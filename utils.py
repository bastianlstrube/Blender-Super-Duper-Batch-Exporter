import bpy
import os

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
        print(f"Error: Start collection '{start_coll_name}' not found.")
        return None
    
    # Get the top-level collection
    top_level_coll = None
    if top_level_coll_name == "Scene Collection":
        if bpy.context and bpy.context.scene:
            top_level_coll = bpy.context.scene.collection
        else:
            print("Error: Cannot access Scene Collection. No active scene context.")
            return None
    else:
        top_level_coll = bpy.data.collections.get(top_level_coll_name)
        if not top_level_coll:
            print(f"Error: Top-level collection '{top_level_coll_name}' not found.")
            return None
    
    print(f"Checking hierarchy for collection: '{start_coll.name}' up to '{top_level_coll_name}'")
    
    # Special case: start collection is the target top-level collection
    if start_coll == top_level_coll:
        print(f"'{start_coll.name}' is the specified top-level collection.")
        return start_coll.name
    
    # Trace the path up the hierarchy
    path = [start_coll.name]
    current_coll = start_coll
    
    while current_coll != top_level_coll:
        parent_coll = find_parent_collection(current_coll)
        
        if not parent_coll:
            print(f"No parent found for '{current_coll.name}'. Hierarchy is incomplete.")
            return None
        
        if parent_coll == top_level_coll:
            hierarchy_path = os.path.join(*reversed(path))
            print(f"Hierarchy path found: {hierarchy_path}")
            return hierarchy_path
        
        path.append(parent_coll.name)
            
        current_coll = parent_coll
    
    # This should not be reached if logic is correct
    return None