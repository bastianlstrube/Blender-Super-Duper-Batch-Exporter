# SPDX-FileCopyrightText: 2016-2024 Bastian L. Strube
#
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "Super Duper Batch Exporter",
    "author": "Bastian L Strube, forked from Mrtripie",
    "blender": (4, 2, 0),
    "category": "Import-Export",
    "location": "Set in preferences below. Default: Top Bar (After File, Edit, ...Help)",
    "description": "Batch export the objects in your scene into seperate files",
    "warning": "Relies on the export add-on for the format used being enabled",
    "doc_url": "https://github.com/bastianlstrube/Blender-Super-Duper-Batch-Exporter",
}
from bpy.types import Scene, TOPBAR_MT_editor_menus, VIEW3D_MT_editor_menus
from bpy.props import PointerProperty
from bpy.utils import register_class, unregister_class, previews
import importlib
import os
import bpy

module_names = [
    "preferences",
    "properties",
    "panels",
    "operators", 
]


def register_unregister_modules(module_names: list, register: bool):
    """Recursively register or unregister modules by looking for either
    un/register() functions or lists named `registry` which should be a list of
    registerable classes.
    """
    register_func = register_class if register else unregister_class
    un = 'un' if not register else ''

    modules = [
    __import__(__package__ + "." + submod, {}, {}, submod)
    for submod in module_names
    ]

    for m in modules:
        if register:
            importlib.reload(m)
        if hasattr(m, 'registry'):
            for c in m.registry:
                try:
                    register_func(c)
                except Exception as e:
                    print(
                        f"Warning: Super Duper Batch Exporter failed to {un}register class: {c.__name__}"
                    )
                    print(e)

        if hasattr(m, 'modules'):
            register_unregister_modules(m.modules, register)

        if register and hasattr(m, 'register'):
            m.register()
        elif not register and hasattr(m, 'unregister'):
            m.unregister()

# icon dict to store.... something in
preview_collections = {}

def register():
    # icon registration
    global preview_collections
    pcoll = previews.new()
    preview_collections["main"] = pcoll 
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    
    # Load both variations
    pcoll.load("batchexport_icon_light", os.path.join(icons_dir, "SuperDuperBatchExporter_Icon.png"), 'IMAGE')
    pcoll.load("batchexport_icon_dark", os.path.join(icons_dir, "SuperDuperBatchExporter_Icon_DarkTheme.png"), 'IMAGE')
    #pcoll.load("batchexport_icon", os.path.join(icons_dir, "SuperDuperBatchExporter_Icon.png"), 'IMAGE')
    
    register_unregister_modules(module_names, True)

    # Add batch export settings to Scene type
    Scene.batch_export = PointerProperty(type=properties.BatchExportSettings)
    
    # Always append the draw_popover function to menus
    TOPBAR_MT_editor_menus.append(panels.draw_popover)
    VIEW3D_MT_editor_menus.append(panels.draw_popover)


def unregister():
    # icon removal
    global preview_collections
    for pcoll in preview_collections.values():
        previews.remove(pcoll)
    preview_collections.clear()
    custom_icons = None # Good practice to clear the global reference

    register_unregister_modules(reversed(module_names), False)

    # Remove the panel from menus
    TOPBAR_MT_editor_menus.remove(panels.draw_popover)
    VIEW3D_MT_editor_menus.remove(panels.draw_popover)

    # Note: Scene.batch_export is intentionally NOT deleted on unregister.
    # Removing it would break access to the user's per-scene settings stored
    # in the .blend file if the addon is re-enabled in the same session.

def is_dark_theme():
    """Calculates the luminance of the UI to determine if the theme is dark."""
    theme = bpy.context.preferences.themes[0]

    # Sample "Themes > User Interface > Tool > Inner"
    bg_color = theme.user_interface.wcol_tool.inner
    
    luminance = (0.299 * bg_color[0]) + (0.587 * bg_color[1]) + (0.114 * bg_color[2])
    return luminance < 0.35

def get_icon_id(icon_name):
    """Helper function to get icon ID, switching based on theme luminance"""
    if "main" in preview_collections:
        pcoll = preview_collections["main"]
        
        # Determine if we need the light or dark version
        # Note: Your register() loads 'batchexport_icon_light' and 'batchexport_icon_dark'
        suffix = "_dark" if is_dark_theme() else "_light"
        theme_icon_name = f"{icon_name}{suffix}"
        
        if theme_icon_name in pcoll:
            return pcoll[theme_icon_name].icon_id
            
    return 0
