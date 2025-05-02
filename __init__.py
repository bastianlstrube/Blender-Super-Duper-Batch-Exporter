# SPDX-FileCopyrightText: 2016-2024 Bastian L. Strube
#
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "Super Duper Batch Exporter",
    "author": "Bastian L Strube, forked from Mrtripie",
    "version": (2, 4, 9),
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
                        f"Warning: Pie Menus failed to {un}register class: {c.__name__}"
                    )
                    print(e)

        if hasattr(m, 'modules'):
            register_unregister_modules(m.modules, register)

        if register and hasattr(m, 'register'):
            m.register()
        elif hasattr(m, 'unregister'):
            m.unregister()

# icon dict to store.... something in
preview_collections = {}

def register():
    # icon registration
    global preview_collections
    pcoll = previews.new()
    custom_icons = pcoll
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    pcoll.load("batchexport_icon", os.path.join(icons_dir, "SuperDuperBatchExporter_Icon.png"), 'IMAGE')
    preview_collections["main"] = pcoll

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
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    custom_icons = None # Good practice to clear the global reference

    register_unregister_modules(reversed(module_names), False)

    # Remove the panel from menus
    TOPBAR_MT_editor_menus.remove(panels.draw_popover)
    VIEW3D_MT_editor_menus.remove(panels.draw_popover)

    # Remove properties
    #del bpy.types.Scene.batch_export  # THIS SHOULD BE ADDED AS A BUTTON IN THE PREFERENCES INSTEAD

def get_icon_id(icon_name):
    """Helper function to get icon ID"""
    if "main" in preview_collections and icon_name in preview_collections["main"]:
        return preview_collections["main"][icon_name].icon_id
    return 0