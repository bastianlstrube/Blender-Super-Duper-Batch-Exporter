import bpy
from pathlib import Path
from bpy.types import PropertyGroup
from bpy.props import (BoolProperty, IntProperty, EnumProperty, StringProperty,
                       FloatVectorProperty, FloatProperty, CollectionProperty,
                       PointerProperty)
from .utils import get_operator_presets, get_preset_index, preset_enum_items_refs
import os
import re

# Set True while the load-time migration runs so reassigning `mode` doesn't fire
# the identity-token swap before the migration has rebuilt the filename itself.
_suppress_mode_update = False

# Which identity token represents the "thing being named" in each mode.
_MODE_IDENTITY = {
    "OBJECTS": "$OBJ",
    "PARENT_OBJECTS": "$OBJ",
    "COLLECTIONS": "$COLL",
    "SCENE": "$BLEND",
}

# Regexes that match each identity token. $COLL uses a negative lookahead so it
# never matches the $COLL_PATH directory token.
_IDENTITY_PATTERNS = {
    "$OBJ": r"\$OBJ",
    "$COLL": r"\$COLL(?!_PATH)",
    "$SCENE": r"\$SCENE",
    "$BLEND": r"\$BLEND",
}


def _swap_identity_token(name, target):
    """Replace whichever identity token is present in the filename leaf with `target`.

    Leaves literal text (prefix/suffix), path tokens like $COLL_PATH, and subdirectories untouched.
    If `target` is already present in the leaf, or no identity token is found, returns `name`
    unchanged so a user's fully custom template is never clobbered.
    """
    # Isolate directory components from the leaf filename
    last_slash_idx = max(name.rfind("/"), name.rfind("\\"))
    if last_slash_idx != -1:
        directory_part = name[:last_slash_idx + 1]
        filename_part = name[last_slash_idx + 1:]
    else:
        directory_part = ""
        filename_part = name

    # Check and swap only inside the leaf filename component
    if re.search(_IDENTITY_PATTERNS[target], filename_part):
        return name
        
    for token, pattern in _IDENTITY_PATTERNS.items():
        if token == target:
            continue
        if re.search(pattern, filename_part):
            filename_part = re.sub(pattern, lambda m: target, filename_part, count=1)
            return directory_part + filename_part
            
    return name


def update_mode_identity_token(self, context):
    """When the mode changes, swap the primary identity token in the filename
    (e.g. $OBJ <-> $COLL <-> $SCENE) so the template stays meaningful."""
    if _suppress_mode_update:
        return
    target = _MODE_IDENTITY.get(self.mode)
    if not target:
        return
    new_name = _swap_identity_token(self.filename, target)
    if new_name != self.filename:
        self.filename = new_name

def update_directory_relative(self, context):
    """
    If a Project Directory is set, try to make the export directory
    relative to it automatically when the user picks a folder.
    """
    addon_name = __package__
    prefs = context.preferences.addons[addon_name].preferences
    if not prefs or not getattr(prefs, 'project_dir', ''):
        return

    project_root = Path(bpy.path.abspath(prefs.project_dir)).resolve()
    current_path = Path(bpy.path.abspath(self.directory)).resolve()

    try:
        relative_path = current_path.relative_to(project_root)
        new_path_str = str(relative_path)
        if new_path_str == '.':
             new_path_str = ""

        if self.directory != new_path_str:
            self.directory = new_path_str
    except ValueError:
        pass

class ExportObjectItem(PropertyGroup):
    object: PointerProperty(name="Object", type=bpy.types.Object)
    collection: PointerProperty(name="Collection", type=bpy.types.Collection)


def get_mode_items(self, context):
    """Dynamically generates export modes, keeping legacy IDs alive for file loading."""
    # Core active items with their original explicit integer values preserved.
    # PARENT_OBJECTS is listed first so it remains the default (a dynamic
    # items callback can't take a `default=`, so the first item is used).
    items = [
        ("PARENT_OBJECTS", "Parent Objects",
         "Same as 'Objects', but objects that are parents have their\nchildren exported along with them", 2),
        ("OBJECTS", "Objects", "Each object is exported separately", 1),
        ("COLLECTIONS", "Collections", "Each collection is exported into its own file", 3),
        ("SCENE", "Scene", "Export the scene into one file\nIf Filename is empty, .blend file name is used.", 6),
    ]

    # Read the raw property value directly from the data block
    current_raw = self.get("mode")

    # If the file contains a legacy mode, expose it to the loader so it won't clamp to 'SCENE'
    if current_raw in {"COLLECTION_SUBDIRECTORIES", 4}:
        items.append(("COLLECTION_SUBDIRECTORIES", "[Legacy] Collection Sub-Directories", "Legacy mode", 4))
    elif current_raw in {"COLLECTION_SUBDIR_PARENTS", 5}:
        items.append(("COLLECTION_SUBDIR_PARENTS", "[Legacy] Collection Sub-Directories By Parent", "Legacy mode", 5))

    return items


class BatchExportSettings(PropertyGroup):
    # File Settings:
    directory: StringProperty(
        name="Directory",
        description="Folder to place the exported files.\nIf a 'Project Directory' is set in Preferences, this is relative to that.\nOtherwise, '//' is relative to the .blend file.",
        default="//",
        subtype='DIR_PATH',
        update=update_directory_relative,
    )
    copy_on_export: BoolProperty(
        name="Make Copies",
        description="Make a copy of exported files in a secondary directory"
    )
    copy_directory: StringProperty(
        name="Copy Dir",
        description="Directory where export files will be copied to",
        default="//",
        subtype='DIR_PATH',
    )
    filename: StringProperty(
        name="Filename",
        description=(
            "Name for each exported file (without the extension).\n"
            "Supports subdirectories with '/' as a universal separator.\n"
            "Use the dropdown to insert tokens:\n"
            "$OBJ (Object), $COLL (Immediate Collection), $COLL_PATH (Full Collection Hierarchy), "
            "$SCENE (Scene), $BLEND (File Name), $DATE (YYYY-MM-DD), $TIME (HHMMSS).\n"
            "If left blank it falls back to the object / collection / .blend name for the mode."
        ),
        default="$OBJ",
    )

    # Export Settings:
    file_format: EnumProperty(
        name="Format",
        description="Which file format to export to",
        items=[
            ("ABC", "Alembic (.abc)", "", 9),
            ("USD", "Universal Scene Description (.usd/.usdc/.usda)", "", 2),
            ("SVG", "Grease Pencil as SVG (.svg)", "", 10),
            ("PDF", "Grease Pencil as PDF (.pdf)", "", 11),
            ("OBJ", "Wavefront (.obj)", "", 7),
            ("PLY", "Stanford (.ply)", "", 3),
            ("STL", "STL (.stl)", "", 4),
            ("FBX", "FBX (.fbx)", "", 5),
            ("glTF", "glTF (.glb/.gltf)", "", 6),
        ],
        default="glTF",
    )
    mode: EnumProperty(
        name="Mode",
        description="What composition method to use for splitting up files",
        items=get_mode_items,
        update=update_mode_identity_token,
    )
    limit: EnumProperty(
        name="Limit to",
        description="How to limit which objects are exported",
        items=[
            ("VISIBLE", "Visible", "", 1),
            ("SELECTED", "Selected", "", 2),
            ("RENDERABLE", "Render Enabled", "", 3),
            ("LIST", "List", "Export only objects added to the custom list", 4),
        ],
    )
    
    # List related Properties
    export_list: CollectionProperty(type=ExportObjectItem)
    export_list_index: IntProperty(name="Active Object Index", default=0)
    use_secondary: BoolProperty(
        name="Extra Limit",
        description="Further limit which objects in list to export"
    )
    secondary_limit: EnumProperty(
        name="Extra Limit",
        description="Filter of objects in list, useful when collections are added to the list",
        items=[
            ('SELECTED', "Selected", "Only selected objects"),
            ('VISIBLE', "Visible", "Only visible objects"),
            ('RENDERABLE', "Renderable", "Only renderable objects"),
        ],
        default='VISIBLE',
    )

    preview_index: IntProperty(
    name="Preview Index",
    default=0,
    description="Index of the object currently being previewed"
    )
    # Note: the old `prefix_collection` and `full_hierarchy` toggles were removed in
    # favour of the $COLL / $COLL_PATH prefix tokens. Older files carrying those values
    # are converted on load by migrate_legacy_batch_export_modes() in __init__.py.


    # Format specific options:
    usd_format: EnumProperty(
        name="Format",
        items=[
            (".usd", "Plain (.usd)", "Can be either binary or ASCII\nIn Blender this exports to binary", 1),
            (".usdc", "Binary Crate (default) (.usdc)", "Binary, fast, hard to edit", 2),
            (".usda", "ASCII (.usda)", "ASCII Text, slow, easy to edit", 3),
        ],
        default=".usdc",
    )
    usd_export_animation: BoolProperty(
        name="Export Animation",
        description="Export the scene's frame range as USD animation",
        default=False,
    )
    gltf_format: EnumProperty(
        name="Format",
        description="Which glTF file variant to export",
        items=[
            ('GLB', "Binary (.glb)", "Single, self-contained binary file", 1),
            ('GLTF_SEPARATE', "Separate (.gltf + .bin + textures)", "Exports the scene, geometry and textures as separate files", 2),
        ],
        default='GLB',
    )
    ply_ascii: BoolProperty(name="ASCII Format", default=False)
    stl_ascii: BoolProperty(name="ASCII Format", default=False)

    # Presets: A string property for saving your option (without new presets changing your choice), and enum property for choosing
    abc_preset: StringProperty(default='NO_PRESET')
    abc_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Alembic (.abc))",
        items=lambda self, context: get_operator_presets('wm.alembic_export'),
        get=lambda self: get_preset_index('wm.alembic_export', self.abc_preset),
        set=lambda self, value: setattr(self, 'abc_preset', preset_enum_items_refs['wm.alembic_export'][value][0]),
    )
    usd_preset: StringProperty(default='NO_PRESET')
    usd_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Universal Scene Description (.usd, .usdc, .usda))",
        items=lambda self, context: get_operator_presets('wm.usd_export'),
        get=lambda self: get_preset_index('wm.usd_export', self.usd_preset),
        set=lambda self, value: setattr(self, 'usd_preset', preset_enum_items_refs['wm.usd_export'][value][0]),
    )
    obj_preset: StringProperty(default='NO_PRESET')
    obj_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Wavefront (.obj))",
        items=lambda self, context: get_operator_presets('wm.obj_export'),
        get=lambda self: get_preset_index('wm.obj_export', self.obj_preset),
        set=lambda self, value: setattr(self, 'obj_preset', preset_enum_items_refs['wm.obj_export'][value][0]),
    )
    fbx_preset: StringProperty(default='NO_PRESET')
    fbx_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > FBX (.fbx))",
        items=lambda self, context: get_operator_presets('export_scene.fbx'),
        get=lambda self: get_preset_index('export_scene.fbx', self.fbx_preset),
        set=lambda self, value: setattr(self, 'fbx_preset', preset_enum_items_refs['export_scene.fbx'][value][0]),
    )
    gltf_preset: StringProperty(default='NO_PRESET')
    gltf_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > glTF (.glb/.gltf))",
        items=lambda self, context: get_operator_presets('export_scene.gltf'),
        get=lambda self: get_preset_index('export_scene.gltf', self.gltf_preset),
        set=lambda self, value: setattr(self, 'gltf_preset', preset_enum_items_refs['export_scene.gltf'][value][0]),
    )

    apply_mods: BoolProperty(
        name="Apply Modifiers",
        description="Should the modifiers by applied onto the exported mesh?\nCan't export Shape Keys with this on",
        default=True,
    )
    frame_start: IntProperty(
        name="Frame Start",
        description="First frame to export",
        default=1,
    )
    frame_end: IntProperty(
        name="Frame End",
        description="Last frame to export",
        default=1,
    )
    object_types: EnumProperty(
        name="Object Types",
        options={'ENUM_FLAG'},
        items=[
            ('MESH', "Mesh", "", 1),
            ('CURVE', "Curve", "", 2),
            ('SURFACE', "Surface", "", 4),
            ('META', "Metaball", "", 8),
            ('FONT', "Text", "", 16),
            ('GPENCIL', "Grease Pencil", "", 32),
            ('ARMATURE', "Armature", "", 64),
            ('EMPTY', "Empty", "", 128),
            ('LIGHT', "Lamp", "", 256),
            ('CAMERA', "Camera", "", 512),
        ],
        description="Which object types to export\n(NOT ALL FORMATS WILL SUPPORT THESE)",
        default={'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'GPENCIL', 'ARMATURE'},
    )

    # Transform:
    set_location: BoolProperty(name="Set Location", default=False)
    location: FloatVectorProperty(name="Location", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    set_rotation: BoolProperty(name="Set Rotation (XYZ Euler)", default=False)
    rotation: FloatVectorProperty(name="Rotation", default=(0.0, 0.0, 0.0), subtype="EULER")
    set_scale: BoolProperty(name="Set Scale", default=False)
    scale: FloatVectorProperty(name="Scale", default=(1.0, 1.0, 1.0), subtype="XYZ")
    apply_location: BoolProperty(
        name="Apply Location", default=False,
        description="Bake the object's location into the mesh data before export",
    )
    apply_rotation: BoolProperty(
        name="Apply Rotation", default=False,
        description="Bake the object's rotation into the mesh data before export",
    )
    apply_scale: BoolProperty(
        name="Apply Scale", default=False,
        description="Bake the object's scale into the mesh data before export",
    )
    corrective_flip_normals: BoolProperty(
        name="Corrective Flip Normals", default=True,
        description="When applying a negative scale, flip mesh normals so faces stay outward-facing",
    )

    # LOD Creation:
    create_lod: BoolProperty(
        name="Create LOD", default=False,
        description="Export Levels of Details for game engines",
    )
    lod_count: IntProperty(
        name="Number of LODs",
        description="How many levels of detail to export",
        default=4, min=1, max=4,
    )
    lod1_ratio: FloatProperty(
        name="LOD 1 Ratio",
        description="Decimate factor for LOD 1",
        default=0.80, min=0.0, max=1.0, subtype="FACTOR"
    )
    lod2_ratio: FloatProperty(
        name="LOD 2 Ratio",
        description="Decimate factor for LOD 2",
        default=0.50, min=0.0, max=1.0, subtype="FACTOR"
    )
    lod3_ratio: FloatProperty(
        name="LOD 3 Ratio",
        description="Decimate factor for LOD 3",
        default=0.20, min=0.0, max=1.0, subtype="FACTOR"
    )
    lod4_ratio: FloatProperty(
        name="LOD 4 Ratio",
        description="Decimate factor for LOD 4",
        default=0.10, min=0.0, max=1.0, subtype="FACTOR"
    )

registry = [
    ExportObjectItem,
    BatchExportSettings,
]
