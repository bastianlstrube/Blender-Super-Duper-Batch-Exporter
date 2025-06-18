import bpy
from bpy.types import AddonPreferences
from bpy.props import EnumProperty, BoolProperty
from . import panels

# Addon settings that are NOT specific to a .blend file
class BatchExportPreferences(AddonPreferences):
    bl_idname = __package__

    def addon_location_updated(self, context):
        bpy.types.TOPBAR_MT_editor_menus.remove(panels.draw_popover)
        bpy.types.VIEW3D_MT_editor_menus.remove(panels.draw_popover)
        if hasattr(bpy.types, "VIEW3D_PT_batch_export"):
            bpy.utils.unregister_class(panels.VIEW3D_PT_batch_export)
        if self.addon_location == 'TOPBAR':
            bpy.types.TOPBAR_MT_editor_menus.append(panels.draw_popover)
        elif self.addon_location == '3DHEADER':
            bpy.types.VIEW3D_MT_editor_menus.append(panels.draw_popover)
        elif self.addon_location == '3DSIDE':
            bpy.utils.register_class(panels.VIEW3D_PT_batch_export)

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
        update=addon_location_updated,
    )
    copy_on_export: BoolProperty(
        name="Copy on Export",
        description="Make a copy of exported files in a secondary directory",
        default=False,
        update=addon_location_updated,
    )
    def draw(self, context):
        self.layout.prop(self, "addon_location")
        self.layout.prop(self, "copy_on_export")

registry = [
    BatchExportPreferences,
]