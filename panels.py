import bpy
from bpy.types import Panel, UIList, Menu
from . import get_icon_id
from . import utils


class BATCH_EXPORT_UL_object_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        if item.object:
            layout.label(text=item.object.name, icon_value=layout.icon(item.object))
        else:
            layout.label(text="(deleted)", icon='ERROR')


class BATCH_EXPORT_MT_token_menu(Menu):
    """Dropdown of naming tokens that get appended to the filename."""
    bl_idname = "BATCH_EXPORT_MT_token_menu"
    bl_label = "Insert Token"

    # (token, human-readable label)
    tokens = (
        ("$OBJ", "Object Name"),
        ("$COLL", "Collection"),
        ("$COLL_PATH", "Collection Hierarchy"),
        ("$SCENE", "Scene Name"),
        ("$BLEND", "Blend File Name"),
        ("$DATE", "Date (YYYY-MM-DD)"),
        ("$TIME", "Time (HHMMSS)"),
        ("/", "Sub-Directory"),
    )

    def draw(self, context):
        layout = self.layout
        for token, label in self.tokens:
            layout.operator(
                "batch_export.insert_token", text=f"{label}   {token}"
            ).token = token


# Draws the .blend file specific settings used in the
# Popover panel or Side Panel panel
def draw_settings(self, context):
    self.layout.use_property_split = False
    self.layout.use_property_decorate = False
    settings = context.scene.batch_export
    self.layout.operator_context = 'INVOKE_DEFAULT'

    copies = False
    name = __package__
    if name in context.preferences.addons:
        copies = context.preferences.addons[name].preferences.copy_on_export

    # Export button + open-folder shortcut
    icon_id = get_icon_id("batchexport_icon")
    row = self.layout.row(align=True)
    if icon_id:
        row.operator('export_mesh.batch', icon_value=icon_id)
    else:
        row.operator('export_mesh.batch', icon='EXPORT')
    row.operator('batch_export.open_directory', text='', icon='FILE_FOLDER')

    # Options
    self.layout.separator()
    col = self.layout.column(align=True)
    col.prop(settings, 'directory')
    if copies and settings.copy_on_export:
        col.prop(settings, 'copy_directory')
    if copies:
        col.prop(settings, 'copy_on_export')
    name_row = col.row(align=True)
    name_row.prop(settings, 'filename')
    name_row.menu("BATCH_EXPORT_MT_token_menu", text='', icon='DOWNARROW_HLT')

    # Greyed-out live preview of the first file that would be exported.
    preview = utils.preview_export_name(context, settings)
    preview_row = col.row()
    preview_row.active = False
    if preview:
        preview_row.label(text=preview, icon='RIGHTARROW_THIN')
    else:
        preview_row.label(text="(no objects match the filter)", icon='RIGHTARROW_THIN')

    self.layout.separator()

    # Export Settings
    col = self.layout.column(align=True)
    col.label(text="Export Settings:")
    col.prop(settings, 'file_format')
    col.prop(settings, 'mode')
    col.prop(settings, 'limit')
    if settings.limit == 'LIST':
        list_row = self.layout.row()
        list_row.template_list(
            "BATCH_EXPORT_UL_object_list", "",
            settings, "export_list",
            settings, "export_list_index",
            rows=10,
        )
        side = list_row.column(align=True)
        side.operator("batch_export.list_add", text="", icon='ADD')
        side.operator("batch_export.list_remove", text="", icon='REMOVE')
        side.separator()
        side.operator("batch_export.list_remove_invalid", text="", icon='TRASH')

    self.layout.separator()

    # Settings
    col = self.layout.column()
    col.label(text=settings.file_format + " Settings:")
    if settings.file_format == 'ABC':
        col.prop(settings, 'abc_preset_enum')
        col.prop(settings, 'frame_start')
        col.prop(settings, 'frame_end')
    elif settings.file_format == 'USD':
        col.prop(settings, 'usd_format')
        col.prop(settings, 'usd_preset_enum')
        col.prop(settings, 'usd_export_animation')
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
        col.prop(settings, 'gltf_format')
        col.prop(settings, 'gltf_preset_enum')
        self.layout.prop(settings, 'apply_mods')
    self.layout.use_property_split = False
    self.layout.separator()

    # Object Types Filter
    self.layout.label(text="Object Types:")
    grid = self.layout.grid_flow(columns=3, align=True)
    grid.prop(settings, 'object_types')
    self.layout.separator()

    # Transform (collapsible)
    header, body = self.layout.panel("sdbe_transform_panel", default_closed=True)
    header.label(text="Transform on Export:")
    if body is not None:
        col = body.column(align=True)
        col.prop(settings, 'apply_location')
        col.prop(settings, 'apply_rotation')
        col.prop(settings, 'apply_scale')
        if settings.apply_scale:
            row = col.row()
            row.separator()
            row.prop(settings, 'corrective_flip_normals')

        col = body.column(align=True)
        col.prop(settings, 'set_location')
        if settings.set_location:
            col.prop(settings, 'location', text="")
        col.prop(settings, 'set_rotation')
        if settings.set_rotation:
            col.prop(settings, 'rotation', text="")
        col.prop(settings, 'set_scale')
        if settings.set_scale:
            col.prop(settings, 'scale', text="")

    # LOD Creation
    if settings.file_format in {'FBX', 'glTF'}:
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
    name = __package__
    if name not in context.preferences.addons:
        return
    location = context.preferences.addons[name].preferences.addon_location

    # draw_popover is appended to both the Top Bar and the 3D Viewport header
    # menus; the menu class name tells us which one we're currently drawing in.
    cls_name = type(self).__name__
    if 'TOPBAR' in cls_name:
        if location != 'TOPBAR':
            return
    elif 'VIEW3D' in cls_name:
        if location != '3DHEADER':
            return
    else:
        return

    icon_id = get_icon_id("batchexport_icon")
    row = self.layout.row(align=True)
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
        name = __package__
        if name in context.preferences.addons:
            return context.preferences.addons[name].preferences.addon_location == '3DSIDE'
        return False

    def draw(self, context):
        draw_settings(self, context)


# Popover panel (used on 3D Viewport Header or Top Bar option)
class POPOVER_PT_batch_export(Panel):
    bl_space_type = 'TOPBAR'
    bl_region_type = 'HEADER'
    bl_label = "Super Duper Batch Exporter"
    bl_ui_units_x = 12

    @classmethod
    def poll(cls, context):
        name = __package__
        if name in context.preferences.addons:
            return context.preferences.addons[name].preferences.addon_location in {'TOPBAR', '3DHEADER'}
        return False

    def draw(self, context):
        draw_settings(self, context)


registry = [
    BATCH_EXPORT_UL_object_list,
    BATCH_EXPORT_MT_token_menu,
    POPOVER_PT_batch_export,
    VIEW3D_PT_batch_export,
]
