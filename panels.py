import bpy
from bpy.types import Panel
from . import get_icon_id
import os

# Get addon name from directory structure
def get_addon_name():
    # Get the path of this file
    path = os.path.dirname(os.path.realpath(__file__))
    # The addon name is typically the name of the directory containing the addon
    return os.path.basename(path)

# Alternate method to get addon name - sometimes more reliable
def get_addon_name_from_bl_info():
    # Try to get the addon name from bl_info in the __init__.py
    import sys
    for mod_name, mod in sys.modules.items():
        if mod_name.startswith(__package__):
            if hasattr(mod, 'bl_info'):
                return mod_name
    return __package__  # Fallback to package name

# Draws the .blend file specific settings used in the
# Popover panel or Side Panel panel
def draw_settings(self, context):
    self.layout.use_property_split = True
    self.layout.use_property_decorate = False
    settings = context.scene.batch_export
    self.layout.operator_context = 'INVOKE_DEFAULT'

    copies = False
    name = __package__
    if name in context.preferences.addons:
        prefs = context.preferences.addons[name].preferences
        if prefs and hasattr(prefs, 'copy_on_export'):
            copies = prefs.copy_on_export

    # Get custom icon
    icon_id = get_icon_id("batchexport_icon")
    if icon_id:
        self.layout.operator('export_mesh.batch', icon_value=icon_id)
    else:
        self.layout.operator('export_mesh.batch', icon='EXPORT')
    self.layout.separator()
    col = self.layout.column(align=True)
    col.prop(settings, 'directory')
    if copies and settings.copy_on_export:
        col.prop(settings, 'copy_directory')
    if copies:
        col.prop(settings, 'copy_on_export')
    col.prop(settings, 'prefix')
    col.prop(settings, 'suffix')
    self.layout.separator()

    # Export Settings
    col = self.layout.column(align=True)
    col.label(text="Export Settings:")
    col.prop(settings, 'file_format')
    col.prop(settings, 'mode')
    col.prop(settings, 'limit')
    if 'OBJECT' in settings.mode:
        col.prop(settings, 'prefix_collection')
    if 'SUBDIR' in settings.mode:
        col.prop(settings, 'full_hierarchy')
    self.layout.separator()

    # Settings
    col = self.layout.column()
    col.label(text=settings.file_format + " Settings:")
    if settings.file_format == 'DAE':
        col.prop(settings, 'dae_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'ABC':
        col.prop(settings, 'abc_preset_enum')
        col.prop(settings, 'frame_start')
        col.prop(settings, 'frame_end')
    elif settings.file_format == 'USD':
        col.prop(settings, 'usd_format')
        col.prop(settings, 'usd_preset_enum')
    elif settings.file_format == 'OBJ':
        col.prop(settings, 'obj_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'PLY':
        col.prop(settings, 'ply_ascii')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'STL':
        col.prop(settings, 'stl_ascii')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'FBX':
        col.prop(settings, 'fbx_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'glTF':
        col.prop(settings, 'gltf_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    elif settings.file_format == 'X3D':
        col.prop(settings, 'x3d_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    self.layout.use_property_split = False
    self.layout.separator()

    # Object Types Filter
    self.layout.label(text="Object Types:")
    grid = self.layout.grid_flow(columns=3, align=True)
    grid.prop(settings, 'object_types')
    self.layout.separator()

    # Transform
    col = self.layout.column(align=True, heading="Transform:")
    col.prop(settings, 'set_location')
    if settings.set_location:
        col.prop(settings, 'location', text="")  # text is redundant
    col.prop(settings, 'set_rotation')
    if settings.set_rotation:
        col.prop(settings, 'rotation', text="")
    col.prop(settings, 'set_scale')
    if settings.set_scale:
        col.prop(settings, 'scale', text="")

    # LOD Creation
    if settings.file_format == 'FBX':
        col = self.layout.column(align=True, heading="Level of Detail:")
        col.prop(settings, 'create_lod')
        if settings.create_lod:
            col.prop(settings, 'lod_count')
            for count in range(settings.lod_count):
                prop_name = f'lod{count+1}_ratio'
                col.prop(settings, prop_name)


# Draws the button and popover dropdown button used in the
# 3D Viewport Header or Top Bar
def draw_popover(self, context):

    # Get custom icon
    icon_id = get_icon_id("batchexport_icon")

    try:
        prefs = None
        name = get_addon_name_from_bl_info()
        if get_addon_name_from_bl_info() in context.preferences.addons:
            prefs = context.preferences.addons[name].preferences

        if not prefs:
            # Fallback: Just show the UI
            row = self.layout.row()
            row = row.row(align=True)
            if icon_id:
                row.operator('export_mesh.batch', text='', icon_value=icon_id).invoke(context, 'DEFAULT')
            else:
                row.operator('export_mesh.batch', text='', icon='EXPORT').invoke(context, 'DEFAULT')
            row.popover(panel='POPOVER_PT_batch_export', text='')
            return

        # Check if we should draw based on menu type
        draw_in_current_menu = False

        if hasattr(self, 'bl_space_type'):
            if self.bl_space_type == 'TOPBAR' and prefs.addon_location == 'TOPBAR':
                draw_in_current_menu = True
            elif self.bl_space_type == 'VIEW_3D' and prefs.addon_location == '3DHEADER':
                draw_in_current_menu = True
        else:
            # If space_type not available, check class name
            if 'TOPBAR' in self.__class__.__name__ and prefs.addon_location == 'TOPBAR':
                draw_in_current_menu = True
            elif 'VIEW3D' in self.__class__.__name__ and prefs.addon_location == '3DHEADER':
                draw_in_current_menu = True

        if draw_in_current_menu:
            row = self.layout.row()
            row = row.row(align=True)
            if icon_id:
                row.operator('export_mesh.batch', text='', icon_value=icon_id)
            else:
                row.operator('export_mesh.batch', text='', icon='EXPORT')
            row.popover(panel='POPOVER_PT_batch_export', text='')
    except Exception as e:
        # Debug output to system console
        print(f"Batch Export addon error in draw_popover: {e}")
        # Fallback: Just draw the UI anyway
        row = self.layout.row()
        row = row.row(align=True)
        if icon_id:
            row.operator('export_mesh.batch', text='', icon_value=icon_id)
        else:
            row.operator('export_mesh.batch', text='', icon='EXPORT')
        row.popover(panel='POPOVER_PT_batch_export', text='')

# Side Panel panel (used with Side Panel option)
class VIEW3D_PT_batch_export(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Export"
    bl_label = "Super Duper Batch Exporter"

    @classmethod
    def poll(cls, context):
        try:

            name = get_addon_name_from_bl_info()
            if name in context.preferences.addons:
                prefs = context.preferences.addons[name].preferences
                # Return true by default if we can't determine preferences
                if not hasattr(prefs, 'addon_location'):
                    return True
                return prefs.addon_location == '3DSIDE'

            # If we can't find preferences, show the panel anyway as a fallback
            return True
        except Exception as e:
            print(f"Batch Export addon error in VIEW3D_PT_batch_export.poll: {e}")
            # If there's an error, show the panel as a fallback
            return True

    def draw(self, context):
        try:
            draw_settings(self, context)
        except Exception as e:
            # Debug output
            print(f"Batch Export addon error in VIEW3D_PT_batch_export.draw: {e}")
            self.layout.label(text="Error loading UI. Check console for details.")

# Popover panel (used on 3D Viewport Header or Top Bar option)
class POPOVER_PT_batch_export(Panel):
    bl_space_type = 'TOPBAR'
    bl_region_type = 'HEADER'
    bl_label = "Super Duper Batch Exporter"

    @classmethod
    def poll(cls, context):
        try:
            # Try multiple methods to get addon name
            name = get_addon_name_from_bl_info()
            if name in context.preferences.addons:
                prefs = context.preferences.addons[name].preferences
                # Return true by default if we can't determine preferences
                if not hasattr(prefs, 'addon_location'):
                    return True
                return prefs.addon_location in ['TOPBAR', '3DHEADER']

            # If we can't find preferences, show the panel anyway as a fallback
            return True
        except Exception as e:
            print(f"Batch Export addon error in POPOVER_PT_batch_export.poll: {e}")
            # If there's an error, show the panel as a fallback
            return True

    def draw(self, context):
        try:
            draw_settings(self, context)
        except Exception as e:
            # Debug output
            print(f"Batch Export addon error in POPOVER_PT_batch_export.draw: {e}")
            self.layout.label(text="Error loading UI. Check console for details.")


registry = [
    POPOVER_PT_batch_export,
    VIEW3D_PT_batch_export,
]
