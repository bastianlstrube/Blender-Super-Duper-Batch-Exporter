import bpy
from bpy.types import AddonPreferences
from bpy.props import EnumProperty, BoolProperty, StringProperty

# Addon settings that are NOT specific to a .blend file
class BatchExportPreferences(AddonPreferences):
    bl_idname = __package__

    addon_location: EnumProperty(
        name="Addon Location",
        description="Where to put the Batch Export Addon UI",
        items=[
            ('TOPBAR', "Top Bar",
             "Place on Blender's Top Bar (Next to File, Edit, Render, Window, Help)"),
            ('3DHEADER', "3D Viewport Header",
             "Place in the 3D Viewport Header (Next to View, Select, Add, etc.)"),
            ('3DSIDE', "3D Viewport Side Panel (Export Tab)",
             "Place in the 3D Viewport's right side panel, in the Export Tab"),
        ],
    )
    project_dir: StringProperty(
        name="Project Directory",
        description="Base path of Directory setting, Leave empty to disable. Unique to this user prefs",
        subtype='DIR_PATH',
    )
    copy_on_export: BoolProperty(
        name="Copy on Export",
        description="Make a copy of exported files in a secondary directory",
        default=False,
    )
    auto_create_dir: BoolProperty(
        name="Disable Prompt to Create Export Folders",
        description="Automatically create the export directory if it doesn't exist, without prompting",
        default=False,
    )
    def draw(self, context):
        self.layout.prop(self, "addon_location")
        self.layout.prop(self, "project_dir")
        self.layout.prop(self, "copy_on_export")
        self.layout.prop(self, "auto_create_dir")

registry = [
    BatchExportPreferences,
]