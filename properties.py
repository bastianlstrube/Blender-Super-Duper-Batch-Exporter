import bpy
from bpy.types import PropertyGroup
from bpy.props import (BoolProperty, IntProperty, EnumProperty, StringProperty, 
                       FloatVectorProperty, FloatProperty)
from .utils import get_operator_presets, get_preset_index, preset_enum_items_refs

# Groups together all the addon settings that are saved in each .blend file
class BatchExportSettings(PropertyGroup):

    # File Settings:
    directory: StringProperty(
        name="Directory",
        description="Which folder to place the exported files\nDefault of // will export to same directory as the blend file (only works if the blend file is saved)",
        default="//",
        subtype='DIR_PATH',
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
        description="Text to put at the beginning of all the exported file names",
    )
    suffix: StringProperty(
        name="Suffix",
        description="Text to put at the end of all the exported file names",
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
        description="What to export",
        items=[
            ("OBJECTS", "Objects", "Each object is exported separately", 1),
            ("PARENT_OBJECTS", "Parent Objects",
             "Same as 'Objects', but objects that are parents have their\nchildren exported along with them", 2),
            ("COLLECTIONS", "Collections",
             "Each collection is exported into its own file", 3),
            ("COLLECTION_SUBDIRECTORIES", "Collection Sub-Directories",
             "Objects are exported inside sub-directories according to their parent collection", 4),
            ("COLLECTION_SUBDIR_PARENTS", "Collection Sub-Directories By Parent",
             "Same as 'Collection Sub-directories', objects that are\nparents have their children exported along with them", 5),
            ("SCENE", "Scene", "Export the scene into one file\nUse prefix or suffix for filename, else .blend file name is used.", 6),
        ],
        default="PARENT_OBJECTS",
    )
    limit: EnumProperty(
        name="Limit to",
        description="How to limit which objects are exported",
        items=[
            ("VISIBLE", "Visible", "", 1),
            ("SELECTED", "Selected", "", 2),
            ("RENDERABLE", "Render Enabled & Visible", "", 3)
        ],
    )
    prefix_collection: BoolProperty(
        name="Prefix Collection Name",
        description="Adds the containing collection's name to the exported file's name, after the 'prefix'"
    )
    full_hierarchy: BoolProperty(
        name="Full Hierarchy",
        description="Create Sub-Directories for the Collection and Parent Collections,\nrecreating the hierarchy"
    )


    # Format specific options:
    usd_format: EnumProperty(
        name="Format",
        items=[
            (".usd", "Plain (.usd)",
             "Can be either binary or ASCII\nIn Blender this exports to binary", 1),
            (".usdc", "Binary Crate (default) (.usdc)",
             "Binary, fast, hard to edit", 2),
            (".usda", "ASCII (.usda)", "ASCII Text, slow, easy to edit", 3),
        ],
        default=".usdc",
    )
    ply_ascii: BoolProperty(name="ASCII Format", default=False)
    stl_ascii: BoolProperty(name="ASCII Format", default=False)

    # Presets: A string property for saving your option (without new presets changing your choice), and enum property for choosing
    abc_preset: StringProperty(default='NO_PRESET')
    abc_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Alembic (.abc))",
        items=lambda self, context: get_operator_presets('wm.alembic_export'),
        get=lambda self: get_preset_index(
            'wm.alembic_export', self.abc_preset),
        set=lambda self, value: setattr(
            self, 'abc_preset', preset_enum_items_refs['wm.alembic_export'][value][0]),
    )
    dae_preset: StringProperty(default='NO_PRESET')
    dae_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Collada (.dae))",
        items=lambda self, context: get_operator_presets('wm.collada_export'),
        get=lambda self: get_preset_index(
            'wm.collada_export', self.dae_preset),
        set=lambda self, value: setattr(
            self, 'dae_preset', preset_enum_items_refs['wm.collada_export'][value][0]),
    )
    usd_preset: StringProperty(default='NO_PRESET')
    usd_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Universal Scene Description (.usd, .usdc, .usda))",
        items=lambda self, context: get_operator_presets('wm.usd_export'),
        get=lambda self: get_preset_index('wm.usd_export', self.usd_preset),
        set=lambda self, value: setattr(
            self, 'usd_preset', preset_enum_items_refs['wm.usd_export'][value][0]),
    )
    obj_preset: StringProperty(default='NO_PRESET')
    obj_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > Wavefront (.obj))",
        items=lambda self, context: get_operator_presets('wm.obj_export'),
        get=lambda self: get_preset_index('wm.obj_export', self.obj_preset),
        set=lambda self, value: setattr(
            self, 'obj_preset', preset_enum_items_refs['wm.obj_export'][value][0]),
    )
    fbx_preset: StringProperty(default='NO_PRESET')
    fbx_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > FBX (.fbx))",
        items=lambda self, context: get_operator_presets('export_scene.fbx'),
        get=lambda self: get_preset_index('export_scene.fbx', self.fbx_preset),
        set=lambda self, value: setattr(
            self, 'fbx_preset', preset_enum_items_refs['export_scene.fbx'][value][0]),
    )
    gltf_preset: StringProperty(default='NO_PRESET')
    gltf_preset_enum: EnumProperty(
        name="Preset", options={'SKIP_SAVE'},
        description="Use export settings from a preset.\n(Create in the export settings from the File > Export > glTF (.glb/.gltf))",
        items=lambda self, context: get_operator_presets('export_scene.gltf'),
        get=lambda self: get_preset_index(
            'export_scene.gltf', self.gltf_preset),
        set=lambda self, value: setattr(
            self, 'gltf_preset', preset_enum_items_refs['export_scene.gltf'][value][0]),
    )

    apply_mods: BoolProperty(
        name="Apply Modifiers",
        description="Should the modifiers by applied onto the exported mesh?\nCan't export Shape Keys with this on",
        default=True,
    )
    frame_start: IntProperty(
        name="Frame Start",
        min=0,
        description="First frame to export",
        default = 1,
    )
    frame_end: IntProperty(
        name="Frame End",
        min=0,
        description="Last frame to export",
        default = 1,
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
    location: FloatVectorProperty(name="Location", default=(
        0.0, 0.0, 0.0), subtype="TRANSLATION")
    set_rotation: BoolProperty(name="Set Rotation (XYZ Euler)", default=False)
    rotation: FloatVectorProperty(
        name="Rotation", default=(0.0, 0.0, 0.0), subtype="EULER")
    set_scale: BoolProperty(name="Set Scale", default=False)
    scale: FloatVectorProperty(
        name="Scale", default=(1.0, 1.0, 1.0), subtype="XYZ")
    
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
    BatchExportSettings,
]