# SPDX-FileCopyrightText: 2016-2024 Bastian L. Strube
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Single source of truth for the version. `bl_info` is not preserved in the
# module namespace when this add-on is loaded through Blender's extension system
# (metadata comes from blender_manifest.toml instead), so the @persistent load
# handler below cannot read `bl_info` at runtime. Reference this constant instead.
ADDON_VERSION = (2, 9, 0)

bl_info = {
    "name": "Super Duper Batch Exporter",
    "author": "Bastian L Strube, forked from Mrtripie",
    "version": ADDON_VERSION,
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
from bpy.app.handlers import persistent

@persistent
def migrate_legacy_batch_export_modes(dummy=None):
    """Converts legacy settings from older files into the current token syntax.

    The old `prefix`, `suffix`, `prefix_collection` and `full_hierarchy` options have
    all been removed; their stored values are read raw here (they no longer exist as
    registered properties) and folded into the single `filename` template.
    """
    # Reassigning `mode` below would otherwise trigger the identity-token swap and
    # rewrite the filename before we've migrated it; suppress that for the duration.
    properties._suppress_mode_update = True
    try:
        _migrate_all_scenes()
    finally:
        properties._suppress_mode_update = False


def _migrate_all_scenes():
    for scene in bpy.data.scenes:
        if not scene or not hasattr(scene, "batch_export"):
            continue

        settings = scene.batch_export
        # Pull raw values directly out of the storage block to catch integer IDs and
        # properties that are no longer registered on the current PropertyGroup.
        raw_mode = settings.get("mode")

        # Work on a local copy of the old prefix; it is now an unregistered raw value.
        old_prefix = settings.get("prefix") or ""

        # 1. Brand-new file: nothing is stored yet. The dynamic-items enum has no
        # item at value 0, so an unset `mode` shows blank instead of defaulting to
        # the first item. Apply the intended default explicitly.
        if raw_mode is None:
            settings.mode = 'PARENT_OBJECTS'

        # 2. Catch legacy string 'SCENE' or corrupted blank/empty states. Only an
        # actually-stored-but-unmappable value reaches here (raw_mode is not None).
        elif raw_mode == 'SCENE' or settings.mode == '':
            # Re-assigning the string 'SCENE' via Python forces Blender to look up
            # the identifier, find the new integer 6, and write it cleanly to the file.
            settings.mode = 'SCENE'
            print(f"[Batch Export] Restored 'SCENE' mode for scene '{scene.name}'.")

        # 3. Intercept legacy modes (String Identifiers or explicit Integer IDs 4 and 5)
        elif raw_mode in {'COLLECTION_SUBDIRECTORIES', 'COLLECTION_SUBDIR_PARENTS', 4, 5}:
            # Pick the path token based on the old full_hierarchy checkbox state
            token = "$COLL_PATH/" if settings.get("full_hierarchy") else "$COLL/"

            # Prepend the directory token to any pre-existing prefix text
            if not old_prefix.startswith(token):
                old_prefix = token + old_prefix

            # Map onto the streamlined structural choices
            if raw_mode in {'COLLECTION_SUBDIRECTORIES', 4}:
                settings.mode = 'OBJECTS'
            elif raw_mode in {'COLLECTION_SUBDIR_PARENTS', 5}:
                settings.mode = 'PARENT_OBJECTS'

            print(f"[Batch Export] Migrated scene '{scene.name}' to the token path syntax.")

        # Legacy "Prefix Collection Name" toggle -> append a $COLL_ token to the prefix,
        # reproducing the old "<Collection>_<name>" filename behaviour.
        if settings.get("prefix_collection"):
            if not old_prefix.endswith("$COLL_"):
                old_prefix = old_prefix + "$COLL_"
            settings["prefix_collection"] = 0
            print(f"[Batch Export] Migrated 'Prefix Collection' in scene '{scene.name}' to a $COLL_ token.")

        # 3. Fold the old prefix/suffix model into the single 'filename' template.
        # Only touch files that actually stored a prefix or suffix; everything else
        # relies on the new property default ($OBJ) plus the runtime fallback.
        if settings.get("filename") is None and (
            settings.get("prefix") is not None or settings.get("suffix") is not None
        ):
            old_suffix = settings.get("suffix") or ""
            mode_now = settings.mode
            if mode_now == 'SCENE':
                # Scene mode used the prefix as the whole name; blank meant the .blend name.
                core = old_prefix if old_prefix else "$BLEND"
            elif mode_now == 'COLLECTIONS':
                core = old_prefix + "$COLL"
            else:  # OBJECTS / PARENT_OBJECTS
                core = old_prefix + "$OBJ"
            settings["filename"] = core + old_suffix
            print(f"[Batch Export] Migrated naming to unified 'filename' for scene '{scene.name}'.")

        # Stamp the current addon version so future loads can tell which version
        # last wrote this file. Only write when it actually changed, to avoid
        # needlessly flagging the .blend as modified on every load.
        current_version = ADDON_VERSION
        if tuple(settings.get("addon_version", (0, 0, 0))) != current_version:
            settings.addon_version = current_version


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

    bpy.app.handlers.load_post.append(migrate_legacy_batch_export_modes)

def unregister():
    # icon removal
    global preview_collections
    for pcoll in preview_collections.values():
        previews.remove(pcoll)
    preview_collections.clear()

    register_unregister_modules(reversed(module_names), False)

    # Remove the panel from menus
    TOPBAR_MT_editor_menus.remove(panels.draw_popover)
    VIEW3D_MT_editor_menus.remove(panels.draw_popover)

    # Note: Scene.batch_export is intentionally NOT deleted on unregister.
    # Removing it would break access to the user's per-scene settings stored
    # in the .blend file if the addon is re-enabled in the same session.

    if migrate_legacy_batch_export_modes in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(migrate_legacy_batch_export_modes)

def is_dark_theme():
    try:
        prefs = bpy.context.preferences
        if not prefs or not prefs.themes:
            return True # Default safe fallback
        theme = prefs.themes[0]
        bg_color = theme.user_interface.wcol_tool.inner
        luminance = (0.299 * bg_color[0]) + (0.587 * bg_color[1]) + (0.114 * bg_color[2])
        return luminance < 0.35
    except Exception:
        return True

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
