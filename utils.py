import bpy
import os
import datetime
from pathlib import Path


def resolve_name_tokens(text, source_obj=None, collection=None):
    """Replaces interpolation tokens and normalizes paths to universal forward slashes.

    Shared by the export operator (for the real file name) and the panel (for the
    greyed-out live preview), so both always agree on the result.
    """
    if not text:
        return ""

    # Enforce universal forward slash paths
    text = text.replace("\\", "/")

    # 1. Blend file token
    blend_name = Path(bpy.data.filepath).with_suffix('').name if bpy.data.is_saved else "Untitled"
    text = text.replace("$BLEND", blend_name)

    # 2. Scene token
    scene_name = bpy.context.scene.name if bpy.context.scene else "Scene"
    text = text.replace("$SCENE", scene_name)

    # 3. Object token
    if source_obj:
        text = text.replace("$OBJ", bpy.path.clean_name(source_obj.name))
    else:
        text = text.replace("$OBJ", "")

    # 4. Collection and hierarchy path tokens
    coll_name = ""
    coll_path = ""

    coll_to_use = collection
    if not coll_to_use and source_obj and source_obj.users_collection:
        coll_to_use = source_obj.users_collection[0]

    if coll_to_use and coll_to_use.name != "Scene Collection":
        coll_name = bpy.path.clean_name(coll_to_use.name)
        hierarchy = get_collection_hierarchy(coll_to_use.name)
        if hierarchy:
            # Sanitize each path component (consistent with $COLL) while
            # preserving the directory structure as forward slashes.
            parts = hierarchy.replace("\\", "/").split("/")
            coll_path = "/".join(bpy.path.clean_name(p) for p in parts if p)
        else:
            coll_path = coll_name

    text = text.replace("$COLL_PATH", coll_path)
    text = text.replace("$COLL", coll_name)

    # 5. Temporal stamps
    now = datetime.datetime.now()
    text = text.replace("$DATE", now.strftime("%Y-%m-%d"))
    text = text.replace("$TIME", now.strftime("%H%M%S"))

    return text


def get_renderable_objects(scene):
    renderable = []
    def check_collection(collection):
        if collection.hide_render:
            return
        for obj in collection.objects:
            if not obj.hide_render:
                renderable.append(obj)
        for child in collection.children:
            check_collection(child)
    check_collection(scene.collection)
    return renderable


def get_filtered_objects(context, settings):
    """The objects that would actually be exported under the current Limit / Type filters."""
    limit = settings.limit
    
    if limit == 'SELECTED':
        source = context.selected_objects[:]
    elif limit == 'VISIBLE':
        source = [obj for obj in context.view_layer.objects if obj.visible_get()]
    elif limit == 'RENDERABLE':
        renderable_names = {obj.name for obj in get_renderable_objects(context.scene)}
        source = [obj for obj in context.view_layer.objects if obj.name in renderable_names]
        
    elif limit == 'LIST':
        # Create a set to handle duplicates automatically
        export_set = set()
        
        # Helper to collect objects recursively
        def add_coll_recursive(coll):
            for obj in coll.objects:
                export_set.add(obj)
            for child in coll.children:
                add_coll_recursive(child)
        
        for item in settings.export_list:
            if item.object:
                export_set.add(item.object)
            if item.collection:
                add_coll_recursive(item.collection)
        
        # Convert set back to a list to maintain compatibility with the rest of the code
        source = list(export_set)

        # Secondary Limit Filter
        if settings.use_secondary:
            secondary = settings.secondary_limit
            if secondary == 'SELECTED':
                secondary_objs = set(context.selected_objects)
                source = [obj for obj in source if obj in secondary_objs]
            elif secondary == 'VISIBLE':
                source = [obj for obj in source if obj.visible_get()]
            elif secondary == 'RENDERABLE':
                renderable_names = {obj.name for obj in get_renderable_objects(context.scene)}
                source = [obj for obj in source if obj.name in renderable_names]

    else:
        source = []

    # Final filter: Ensures we only return objects that match the user's "Include" settings
    return [obj for obj in source if obj.type in settings.object_types]


def _fallback_to_default(resolved, default_name):
    """Mirror the operator's behaviour: if a template resolves to nothing usable,
    fall back to the mode's natural (object / collection / .blend) name."""
    if not resolved.strip():
        return bpy.path.clean_name(default_name)
    
    # Normalize path formatting to forward slashes
    normalized = resolved.replace("\\", "/")

    # Strip accidental leading slashes caused by unresolved tokens
    while normalized.startswith("/"):
        normalized = normalized[1:]
        
    # If stripping left us with nothing, use the default name
    if not normalized.strip():
        return bpy.path.clean_name(default_name)
    
    # If the path ends with a slash or the filename token is empty/whitespace
    if normalized.endswith("/") or not normalized.split("/")[-1].strip():
        return normalized + bpy.path.clean_name(default_name)
        
    return resolved


def get_export_extension(settings):
    """The file extension (including the dot) that the current format will write."""
    fmt = settings.file_format
    if fmt == 'glTF':
        return '.glb' if settings.gltf_format == 'GLB' else '.gltf'
    if fmt == 'USD':
        return settings.usd_format
    return {
        'FBX': '.fbx',
        'ABC': '.abc',
        'OBJ': '.obj',
        'PLY': '.ply',
        'STL': '.stl',
        'SVG': '.svg',
        'PDF': '.pdf',
    }.get(fmt, '')

def get_unique_preview_paths(context, settings):
    """Returns a list of all unique file paths that would be generated."""
    # Assuming you already have a way to generate jobs (like in your operator)
    # You can reuse the logic that determines the export path for each object/collection
    # Here is a simplified version:
    paths = []
    objs = get_filtered_objects(context, settings)
    
    for obj in objs:
        # Replicate your naming logic
        coll = obj.users_collection[0] if obj.users_collection else None
        path = resolve_name_tokens(settings.filename, obj, coll)
        if path not in paths:
            paths.append(path)
    return paths

def preview_export_name(context, settings):
    """
    Resolve the filename template for the object at the current preview_index.
    Returns: (exact_name_with_extension, has_unresolved_tokens, idx)
    """
    mode = settings.mode
    ext = get_export_extension(settings)
    filename_template = settings.filename

    if mode == 'SCENE':
        blend = Path(bpy.data.filepath).with_suffix('').name if bpy.data.is_saved else "Untitled"
        resolved = resolve_name_tokens(filename_template, None, None)
        has_warning = any(t in filename_template for t in ("$OBJ", "$COLL", "$COLL_PATH"))
        return _fallback_to_default(resolved, blend) + ext, has_warning, 0

    # 1. Get unique paths for the cycling index
    unique_paths = get_unique_preview_paths(context, settings)
    if not unique_paths:
        return "", False, 0
    idx = settings.preview_index % len(unique_paths)
    
    # 2. Get all objects to help resolve the context for the current path
    objs = get_filtered_objects(context, settings)
    if not objs:
        return "", False, 0

    # 3. Resolve context (source_obj/collection) based on the first object 
    # that matches the resolved path (to keep the preview consistent)
    source_obj = None
    collection = None
    
    # Find an object that maps to the currently selected unique path
    for obj in objs:
        coll = obj.users_collection[0] if obj.users_collection else None
        if resolve_name_tokens(filename_template, obj, coll) == unique_paths[idx]:
            source_obj = obj
            collection = coll
            break

    # 4. Handle Parent Objects logic
    if mode == 'PARENT_OBJECTS' and source_obj:
        object_set = set(objs)
        while source_obj.parent and source_obj.parent in object_set:
            source_obj = source_obj.parent
            if source_obj.users_collection:
                collection = source_obj.users_collection[0]

    resolved = resolve_name_tokens(filename_template, source_obj, collection)

    # Mirror the operator's fallback name so a blank/empty template previews the
    # same thing it would actually export (the object's or collection's name),
    # not a placeholder.
    if mode == 'COLLECTIONS':
        default_name = collection.name if collection else (source_obj.name if source_obj else "default")
    else:  # OBJECTS / PARENT_OBJECTS
        default_name = source_obj.name if source_obj else "default"

    # Check for warnings
    has_warning = False
    if "$OBJ" in filename_template and not source_obj:
        has_warning = True
    if "$COLL" in filename_template or "$COLL_PATH" in filename_template:
        if not collection or collection.name == "Scene Collection":
            has_warning = True

    return _fallback_to_default(resolved, default_name) + ext, has_warning, idx


def resolve_base_dir(settings, prefs):
    """
    Calculates the absolute base directory for exports.
    If a project_dir preference is set, it acts as the root and
    settings.directory is treated as relative to it.
    Raises ValueError if the path cannot be resolved (e.g. unsaved .blend
    with a relative output directory and no project dir set).
    """
    project_dir_raw = getattr(prefs, 'project_dir', '')

    if project_dir_raw:
        # Project Directory overrides the .blend file as the relative root.
        project_root = Path(bpy.path.abspath(project_dir_raw))

        relative_part = settings.directory
        # Strip Blender's '//' relative prefix so pathlib joins correctly.
        if relative_part.startswith('//'):
            relative_part = relative_part[2:]
        elif relative_part.startswith('\\'):
            relative_part = relative_part[1:]

        return (project_root / relative_part).resolve()

    # Standard Blender behaviour: relative to the .blend file.
    if settings.directory.startswith('//') and not bpy.data.is_saved:
        raise ValueError(
            "Save the .blend file before exporting to a relative directory,\n"
            "or set a Project Directory in Preferences."
        )
    return Path(bpy.path.abspath(settings.directory)).resolve()

def ensure_directory_exists(path: Path):
    """Safely creates the directory tree if it doesn't exist."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

# A Dictionary of operator_name: [list of preset EnumProperty item tuples].
# Blender's doc warns that not keeping reference to enum props array can
# cause crashs and weird issues.
# Also useful for the get_preset_index function.
preset_enum_items_refs = {}

# Returns a list of tuples used for an EnumProperty's items (identifier, name, description)
# identifier, and name are the file name of the preset without the file extension (.py)
def get_operator_presets(operator):
    presets = [('NO_PRESET', "(no preset)", "", 0)]
    for d in bpy.utils.script_paths(subdir="presets/operator/" + operator):
        for f in os.listdir(d):
            if not f.endswith(".py"):
                continue
            f = os.path.splitext(f)[0]
            presets.append((f, f, ""))
    # Blender's doc warns that not keeping reference to enum props array can
    # cause crashs and weird issues:
    preset_enum_items_refs[operator] = presets
    return presets

# Returns a dictionary of options from an operator's preset.
# When calling an operator's method, you can use ** before a dictionary
# in the method's arguments to set the arguments from that dictionary's
# key: value pairs. Example:
# bpy.ops.category.operator(**options)
def load_operator_preset(operator, preset):
    options = {}
    if preset == 'NO_PRESET':
        return options

    for d in bpy.utils.script_paths(subdir="presets/operator/" + operator):
        fp = "".join([d, "/", preset, ".py"])
        if os.path.isfile(fp):  # Found the preset file
            print("Using preset " + fp)
            file = open(fp, 'r')
            for line in file.readlines():
                # This assumes formatting of these files remains exactly the same
                if line.startswith("op."):
                    line = line.removeprefix("op.")
                    split = line.split(" = ")
                    key = split[0]
                    value = split[1]
                    options[key] = eval(value)
            file.close()
            return options
    # If it didn't find the preset, use empty options
    # (the preset option should look blank if the file doesn't exist anyway)
    return options

# Finds the index of a preset with preset_name and returns it
# Useful for transferring the value of a saved preset (in a StringProperty)
# to the NOT saved EnumProperty for that preset used to present a nice GUI.
def get_preset_index(operator, preset_name):
    for p in range(len(preset_enum_items_refs[operator])):
        if preset_enum_items_refs[operator][p][0] == preset_name:
            return p
    return 0

def find_parent_collection(target_coll):
    """
    Finds the immediate parent collection of a given collection within the scene.
    
    Args:
        target_coll (bpy.types.Collection): The collection whose parent is to be found.
        
    Returns:
        bpy.types.Collection or None: The parent collection, or None if no parent
        is found (e.g., orphaned, or already the scene collection).
    """
    # Check if target is a direct child of the scene collection
    scene_collection = bpy.context.scene.collection
    if target_coll in scene_collection.children.values():
        return scene_collection
    
    # Check all other collections
    for coll in bpy.data.collections:
        if coll != target_coll and target_coll in coll.children.values():
            return coll
            
    return None


def get_collection_hierarchy(start_coll_name, top_level_coll_name="Scene Collection"):
    """
    Traces the hierarchy path from a start collection up to a specified top-level collection.
    
    Args:
        start_coll_name (str): The name of the collection to start from.
        top_level_coll_name (str, optional): The name of the target top-level collection.
            Defaults to "Scene Collection".
            
    Returns:
        str or None: Path string showing the collection hierarchy, or None if path not found.
    """
    # Get the starting collection
    start_coll = bpy.data.collections.get(start_coll_name)
    if not start_coll:
        return None

    # Get the top-level collection
    top_level_coll = None
    if top_level_coll_name == "Scene Collection":
        if bpy.context and bpy.context.scene:
            top_level_coll = bpy.context.scene.collection
        else:
            return None
    else:
        top_level_coll = bpy.data.collections.get(top_level_coll_name)
        if not top_level_coll:
            return None

    # Special case: start collection is the target top-level collection
    if start_coll == top_level_coll:
        return start_coll.name

    # Trace the path up the hierarchy
    path = [start_coll.name]
    current_coll = start_coll

    while current_coll != top_level_coll:
        parent_coll = find_parent_collection(current_coll)

        if not parent_coll:
            return None

        if parent_coll == top_level_coll:
            return os.path.join(*reversed(path))

        path.append(parent_coll.name)

        current_coll = parent_coll

    # This should not be reached if logic is correct
    return None