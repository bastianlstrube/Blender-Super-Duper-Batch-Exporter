import bpy
from pathlib import Path
from bpy.types import PropertyGroup
from bpy.props import (BoolProperty, IntProperty, EnumProperty, StringProperty,
                       FloatVectorProperty, FloatProperty, CollectionProperty,
                       PointerProperty)
from .utils import get_operator_presets, get_preset_index, preset_enum_items_refs
import os

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


def get_mode_items(self, context):
    """Dynamically generates export modes, hiding legacy options from the UI."""
    # PARENT_OBJECTS is placed first so Blender naturally uses it as the default choice
    items = [
        ("PARENT_OBJECTS", "Parent Objects",
         "Same as 'Objects', but objects that are parents have their\nchildren exported along with them", 1),
        ("OBJECTS", "Objects", "Each object is exported separately", 2),
        ("COLLECTIONS", "Collections", "Each collection is exported into its own file", 3),
        ("SCENE", "Scene", "Export the scene into one file\nUse prefix or suffix for filename, else .blend file name is used.", 4),
    ]
    
    # Check underlying IDProperty storage for legacy states during file load
    current_raw = self.get("mode")
    if current_raw == "COLLECTION_SUBDIRECTORIES":
        items.append(("COLLECTION_SUBDIRECTORIES", "[Legacy] Collection Sub-Directories", "Legacy mode being migrated", 5))
    elif current_raw == "COLLECTION_SUBDIR_PARENTS":
        items.append(("COLLECTION_SUBDIR_PARENTS", "[Legacy] Collection Sub-Directories By Parent", "Legacy mode being migrated", 6))
        
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
    prefix: StringProperty(
        name="Prefix",
        description=(
            "Text to put at the beginning of all exported file names.\n"
            "Supports subdirectories with '/' as a universal separator.\n"
            "Tokens: $OBJ (Object), $COLL (Immediate Collection), $COLL_PATH (Full Collection Hierarchy), "
            "$SCENE (Scene), $BLEND (File Name), $DATE (YYYY-MM-DD), $TIME (HHMMSS)"
        ),
    )
    suffix: StringProperty(
        name="Suffix",
        description=(
            "Text to put at the end of all exported file names.\n"
            "Supports subdirectories with '/' as a universal separator.\n"
            "Tokens: $OBJ, $COLL, $COLL_PATH, $SCENE, $BLEND, $DATE, $TIME"
        ),
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
    export_list: CollectionProperty(type=ExportObjectItem)
    export_list_index: IntProperty(name="Active Object Index", default=0)
    prefix_collection: BoolProperty(
        name="Prefix Collection Name",
        description="Adds the containing collection's name to the exported file's name, after the 'prefix'"
    )
    full_hierarchy: BoolProperty(
        name="Full Hierarchy",
        description="Legacy setting used to preserve folder tree states during migration conversions."
    )

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

    # Presets:
    abc_preset: StringProperty(default='NO_PRESET')
    abc_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.",
        items=lambda self, context: get_operator_presets('wm.alembic_export'),
        get=lambda self: get_preset_index('wm.alembic_export', self.abc_preset),
        set=lambda self, value: setattr(self, 'abc_preset', preset_enum_items_refs['wm.alembic_export'][value][0]),
    )
    usd_preset: StringProperty(default='NO_PRESET')
    usd_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.",
        items=lambda self, context: get_operator_presets('wm.usd_export'),
        get=lambda self: get_preset_index('wm.usd_export', self.usd_preset),
        set=lambda self, value: setattr(self, 'usd_preset', preset_enum_items_refs['wm.usd_export'][value][0]),
    )
    obj_preset: StringProperty(default='NO_PRESET')
    obj_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.",
        items=lambda self, context: get_operator_presets('wm.obj_export'),
        get=lambda self: get_preset_index('wm.obj_export', self.obj_preset),
        set=lambda self, value: setattr(self, 'obj_preset', preset_enum_items_refs['wm.obj_export'][value][0]),
    )
    fbx_preset: StringProperty(default='NO_PRESET')
    fbx_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.",
        items=lambda self, context: get_operator_presets('export_scene.fbx'),
        get=lambda self: get_preset_index('export_scene.fbx', self.fbx_preset),
        set=lambda self, value: setattr(self, 'fbx_preset', preset_enum_items_refs['export_scene.fbx'][value][0]),
    )
    gltf_preset: StringProperty(default='NO_PRESET')
    gltf_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.",
        items=lambda self, context: get_operator_presets('export_scene.gltf'),
        get=lambda self: get_preset_index('export_scene.gltf', self.gltf_preset),
        set=lambda self, value: setattr(self, 'gltf_preset', preset_enum_items_refs['export_scene.gltf'][value][0]),
    )

    apply_mods: BoolProperty(name="Apply Modifiers", default=True)
    frame_start: IntProperty(name="Frame Start", default=1)
    frame_end: IntProperty(name="Frame End", default=1)
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
        default={'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'GPENCIL', 'ARMATURE'},
    )

    # Transform:
    set_location: BoolProperty(name="Set Location", default=False)
    location: FloatVectorProperty(name="Location", default=(0.0, 0.0, 0.0), subtype="TRANSLATION")
    set_rotation: BoolProperty(name="Set Rotation (XYZ Euler)", default=False)
    rotation: FloatVectorProperty(name="Rotation", default=(0.0, 0.0, 0.0), subtype="EULER")
    set_scale: BoolProperty(name="Set Scale", default=False)
    scale: FloatVectorProperty(name="Scale", default=(1.0, 1.0, 1.0), subtype="XYZ")
    apply_location: BoolProperty(name="Apply Location", default=False)
    apply_rotation: BoolProperty(name="Apply Rotation", default=False)
    apply_scale: BoolProperty(name="Apply Scale", default=False)
    corrective_flip_normals: BoolProperty(name="Corrective Flip Normals", default=True)

    # LOD Creation:
    create_lod: BoolProperty(name="Create LOD", default=False)
    lod_count: IntProperty(name="Number of LODs", default=4, min=1, max=4)
    lod1_ratio: FloatProperty(name="LOD 1 Ratio", default=0.80, min=0.0, max=1.0, subtype="FACTOR")
    lod2_ratio: FloatProperty(name="LOD 2 Ratio", default=0.50, min=0.0, max=1.0, subtype="FACTOR")
    lod3_ratio: FloatProperty(name="LOD 3 Ratio", default=0.20, min=0.0, max=1.0, subtype="FACTOR")
    lod4_ratio: FloatProperty(name="LOD 4 Ratio", default=0.10, min=0.0, max=1.0, subtype="FACTOR")

registry = [
    ExportObjectItem,
    BatchExportSettings,
]