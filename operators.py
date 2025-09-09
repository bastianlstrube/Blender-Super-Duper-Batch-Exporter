import bpy
import os
from pathlib import Path
import shutil

from bpy.types import Operator
from . import utils

# Operator called when pressing the batch export button.
class EXPORT_MESH_OT_batch(Operator):
    """Export many objects to seperate files all at once"""
    bl_idname = "export_mesh.batch"
    bl_label = "Batch Export"
    file_count = 0
    copy_count = 0

    def execute(self, context):
        settings = context.scene.batch_export

        # Set Base Directory
        base_dir = settings.directory
        if not bpy.data.is_saved:  # Then the blend file hasn't been saved
            # Then the path should be relative
            if base_dir != bpy.path.abspath(base_dir):
                self.report(
                    {'ERROR'}, "Save .blend file somewhere before exporting to relative directory\n(or use an absolute directory)")
                return {'FINISHED'}
        base_dir = bpy.path.abspath(base_dir)  # convert to absolute path
        if not os.path.isdir(base_dir):
            self.report({'ERROR'}, "Export directory doesn't exist")
            return {'FINISHED'}

        self.file_count = 0

        # Save current state of viewlayer, selection and active object to restore after export
        view_layer = context.view_layer
        selection = context.selected_objects
        obj_active = view_layer.objects.active   

        # Check if we're not in Object mode and set if needed
        obj_active = view_layer.objects.active        
        mode = ''
        if obj_active:
            mode = obj_active.mode
            bpy.ops.object.mode_set(mode='OBJECT')  # Only works in Object mode
        

        ##### EXPORT OBJECTS BASED ON MODES #####
        if settings.mode == 'OBJECTS':
            for obj in self.get_filtered_objects(context, settings):

                # Export Selection
                obj.select_set(True)
                self.export_selection(obj.name, context, base_dir)

                # Deselect Obj
                obj.select_set(False)

        elif settings.mode == 'PARENT_OBJECTS':
            exportObjects = self.get_filtered_objects(context, settings)

            for obj in exportObjects:
                if obj.parent in exportObjects:
                    continue  # if it has a parent, skip it for now, it'll be exported when we get to its parent

                # Export Selection
                obj.select_set(True)
                self.select_children_recursive(obj, context,)

                if context.selected_objects:
                    self.export_selection(obj.name, context, base_dir)

                # Deselect
                for obj in context.selected_objects:
                    obj.select_set(False)

        elif settings.mode == 'COLLECTIONS':
            exportobjects = self.get_filtered_objects(context, settings)

            for col in bpy.data.collections.values():
                # Check if collection objects are in filtered objects
                for obj in col.objects:
                    if not obj in exportobjects:
                        continue
                    obj.select_set(True)
                if context.selected_objects:
                    self.export_selection(col.name, context, base_dir)

                # Deselect
                for obj in context.selected_objects:
                    obj.select_set(False)

        # Functionality for both COLLECTION_SUBDIRECTORIES and COLLECTION_SUBDIR_PARENTS
        elif 'COLLECTION_SUBDIR' in settings.mode:
            exportobjects = self.get_filtered_objects(context, settings)

            for obj in exportobjects:
                if 'PARENT' in settings.mode and obj.parent in exportobjects:
                    continue  # if it has a parent, skip it for now, it'll be exported when we get to its parent

                # Modify base_dir to add collection, creating directory if necessary
                sCollection = obj.users_collection[0].name
                if sCollection != "Scene Collection":
                    if settings.full_hierarchy:
                        hierarchy = utils.get_collection_hierarchy(sCollection)
                        collection_dir = os.path.join(base_dir, hierarchy)
                    else:
                        collection_dir = os.path.join(base_dir, sCollection)

                    # create sub-directory if it doesn't exist
                    if not os.path.exists(collection_dir):
                        try:
                            os.makedirs(collection_dir)
                            print(f"Directory created: {collection_dir}")
                        except OSError as e:
                            self.report({'ERROR'}, f"Error creating directory {collection_dir}: {e}")
                else: # If object is just in Scene Collection it get's exported to base_dir
                    collection_dir = base_dir

                # Select
                obj.select_set(True)
                if 'PARENT' in settings.mode:
                    self.select_children_recursive(obj, context)

                # Export
                self.export_selection(obj.name, context, collection_dir)

                # Deselect
                for obj in context.selected_objects:
                    obj.select_set(False)

        elif settings.mode == 'SCENE':
            prefix = settings.prefix
            suffix = settings.suffix
            
            filename = ''
            if not prefix and not suffix:
                filename = bpy.path.basename(bpy.context.blend_data.filepath).split('.')[0]
            
            for obj in self.get_filtered_objects(context, settings):
                obj.select_set(True)
            self.export_selection(filename, context, base_dir)

        # Return selection to how it was
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selection:
            obj.select_set(True)
        view_layer.objects.active = obj_active

        # Return to whatever mode the user was in
        if obj_active:
            bpy.ops.object.mode_set(mode=mode)

        # Report results
        copies = False
        name = __package__
        if name in context.preferences.addons:
            prefs = context.preferences.addons[name].preferences
            if prefs and hasattr(prefs, 'copy_on_export'):
                copies = prefs.copy_on_export

        if self.file_count == 0:
            self.report({'ERROR'}, "NOTHING TO EXPORT")
        elif copies and settings.copy_on_export:
            self.report({'INFO'}, f"Exported {self.file_count} file(s),\nMade {self.copy_count} copies")
        elif self.file_count:
            self.report({'INFO'}, f"Exported {self.file_count} file(s)")

        return {'FINISHED'}

    # Finds all renderable objects and returns a list of them
    def get_renderable_objects(self):
        """
        Recursively collect hidden objects from scene collections.
        
        Returns:
            list: A list of objects hidden in viewport or render
        """
        renderable_objects = []
        
        def check_collection(collection):
            # Skip if collection is None
            if not collection:
                return
            
            # Skip if the entire collection is hidden in render
            if collection.hide_render:
                return
            
            # Check objects in this collection
            for obj in collection.objects:
                # Check both viewport and render visibility
                if not obj.hide_render:
                    renderable_objects.append(obj)
            
            # Recursively check child collections
            while collection.children:
                for child_collection in collection.children:
                    # Skip child collections that are hidden in render
                    if not child_collection.hide_render:
                        check_collection(child_collection)
                break  # Use break to match the while loop structure
        
        # Start the recursive check from the scene's root collection
        check_collection(bpy.context.scene.collection)
        
        return renderable_objects

    # Deselect and Get Objects to Export by Limit Settings
    def get_filtered_objects(self, context, settings):
        objects = context.view_layer.objects.values()
        if settings.limit == 'VISIBLE':
            filtered_objects = []
            for obj in objects:
                obj.select_set(False)
                if obj.visible_get() and obj.type in settings.object_types:
                    filtered_objects.append(obj)
            return filtered_objects
        if settings.limit == 'SELECTED':
            selection = context.selected_objects
            filtered_objects = []
            for obj in objects:
                obj.select_set(False)
                if obj in selection:
                    if obj.type in settings.object_types:
                        filtered_objects.append(obj)
            return filtered_objects
        if settings.limit == 'RENDERABLE':
            filtered_objects = []
            for obj in objects:
                obj.select_set(False)
                if obj.visible_get() and obj.type in settings.object_types:
                    if obj in self.get_renderable_objects():
                        filtered_objects.append(obj)
            return filtered_objects
        return objects

    def select_children_recursive(self, obj, context):
        for c in obj.children:
            if obj.type in context.scene.batch_export.object_types:
                c.select_set(True)
            self.select_children_recursive(c, context)

    def export_selection(self, itemname, context, base_dir):
        settings = context.scene.batch_export
        # save the transform to be reset later:
        old_locations = []
        old_rotations = []
        old_scales = []
        
        # Extra objects for LOD export store for later removal
        preLodObjects = []
        lodObjects = []

        objectsloop = context.selected_objects
        for obj in objectsloop:
            # Save Old Locations
            old_locations.append(obj.location.copy())
            old_rotations.append(obj.rotation_euler.copy())
            old_scales.append(obj.scale.copy())

            # If exporting by parent, don't set child (object that has a parent) transform
            if "PARENT" in settings.mode and obj.parent in context.selected_objects:
                continue
            else:
                if settings.set_location:
                    obj.location = settings.location
                if settings.set_rotation:
                    obj.rotation_euler = settings.rotation
                if settings.set_scale:
                    obj.scale = settings.scale

            # Change Itemname If Collection As Prefix
            if settings.prefix_collection and 'OBJECT' in settings.mode:
                collection_name = obj.users_collection[0].name
                if not collection_name == 'Scene Collection':
                    itemname = "_".join([collection_name, itemname])

            # LOD Creation
            if settings.create_lod and settings.file_format == 'FBX' and obj.type == 'MESH':
                # Save obj info and backup
                obj_CollectionObjs = obj.users_collection[0].objects
                name = obj.name
                obj.name = name + '_preLOD'
                preLodObjects.append(obj)
                obj.select_set(False)

                # Setup LOD parent object
                lodParent = bpy.data.objects.new("Empty_Name", None)
                obj_CollectionObjs.link(lodParent)
                lodParent.location = obj.location
                lodParent.rotation_quaternion = obj.rotation_quaternion
                lodParent.name = name
                lodParent["fbx_type"] = "LodGroup"
                if obj.parent:
                    lodParent.parent = obj.parent
                lodObjects.append(lodParent)
                lodParent.select_set(True)

                # Create LOD0 copy
                lod0 = obj.copy()
                lod0.data = lod0.data.copy() # linked = false
                lod0.name = name + f"_LOD0"
                lod0.parent = lodParent
                lod0.location = (0,0,0)
                obj_CollectionObjs.link(lod0)
                lodObjects.append(lod0)
                lod0.select_set(True)

                # Loop over and create each LOD object
                for lodcount in range(settings.lod_count):
                    lod = lod0.copy()
                    lod.data = lod.data.copy() # linked = false
                    lod.name = name + f"_LOD{lodcount+1}"
                    lod.parent = lodParent
                    obj_CollectionObjs.link(lod)
                    lodObjects.append(lod)
                    lod.select_set(True)

                    # Decimation
                    decimate_mod = lod.modifiers.new('lodding', type='DECIMATE')
                    ratio_attr_name = f"lod{lodcount+1}_ratio"
                    decimate_mod.ratio = getattr(settings, ratio_attr_name)
                    
                    #bpy.ops.object.modifier_apply(modifier=decimate_mod.name)
                settings.apply_mods = True
                # THIS DOESNT WORK settings.object_types.EMPTY = True


        prefix = settings.prefix
        suffix = settings.suffix
        name = prefix + bpy.path.clean_name(itemname) + suffix
        fp = os.path.join(base_dir, name)
        extension = None
        # Export

        if settings.file_format == "ABC":
            extension = '.abc'
            options = utils.load_operator_preset(
                'wm.alembic_export', settings.abc_preset)
            options["filepath"] = fp+extension
            options["selected"] = True
            options["start"] = settings.frame_start
            options["end"] = settings.frame_end
            # By default, alembic_export operator runs in the background, this messes up batch
            # export though. alembic_export has an "as_background_job" arg that can be set to
            # false to disable it, but its marked deprecated, saying that if you EXECUTE the
            # operator rather than INVOKE it it runs in the foreground. Here I change the
            # execution context to EXEC_REGION_WIN.
            # docs.blender.org/api/current/bpy.ops.html?highlight=exec_default#execution-context
            bpy.ops.wm.alembic_export('EXEC_REGION_WIN', **options)

        elif settings.file_format == "USD":
            extension = settings.usd_format
            options = utils.load_operator_preset(
                'wm.usd_export', settings.usd_preset)
            options["filepath"] = fp+extension
            options["selected_objects_only"] = True
            bpy.ops.wm.usd_export(**options)

        elif settings.file_format == "SVG":
            extension = '.svg'
            bpy.ops.wm.gpencil_export_svg(
                filepath=fp+extension, selected_object_type='SELECTED')

        elif settings.file_format == "PDF":
            extension = '.pdf'
            bpy.ops.wm.gpencil_export_pdf(
                filepath=fp+extension, selected_object_type='SELECTED')

        elif settings.file_format == "OBJ":
            extension = '.obj'
            options = utils.load_operator_preset(
                'wm.obj_export', settings.obj_preset)
            options["filepath"] = fp+extension
            options["export_selected_objects"] = True
            options["apply_modifiers"] = settings.apply_mods
            bpy.ops.wm.obj_export(**options)

        elif settings.file_format == "PLY":
            extension = '.ply'
            bpy.ops.wm.ply_export(
                filepath=fp+extension, ascii_format=settings.ply_ascii, export_selected_objects=True, apply_modifiers=settings.apply_mods)

        elif settings.file_format == "STL":
            extension = '.stl'
            bpy.ops.wm.stl_export(
                filepath=fp+extension, ascii_format=settings.stl_ascii, export_selected_objects=True, apply_modifiers=settings.apply_mods)

        elif settings.file_format == "FBX":
            extension = '.fbx'
            options = utils.load_operator_preset(
                'export_scene.fbx', settings.fbx_preset)
            options["filepath"] = fp+extension
            options["use_selection"] = True
            options["use_mesh_modifiers"] = settings.apply_mods
            bpy.ops.export_scene.fbx(**options)

            # LOD De-Creation
            if settings.create_lod:
                for lod in lodObjects:
                    bpy.data.objects.remove(lod, do_unlink=True)
                for obj in preLodObjects:
                    if '_preLOD' in obj.name:
                        obj.name = obj.name[0:-7]
                        

        elif settings.file_format == "glTF":
            extension = '.glb'
            options = utils.load_operator_preset(
                'export_scene.gltf', settings.gltf_preset)
            options["filepath"] = fp
            options["use_selection"] = True
            options["export_apply"] = settings.apply_mods
            bpy.ops.export_scene.gltf(**options)
            print(options.keys())

        # Reset the transform to what it was before
        i = 0
        for obj in context.selected_objects:
            obj.location = old_locations[i]
            obj.rotation_euler = old_rotations[i]
            obj.scale = old_scales[i]
            i += 1

        print("exported: ", fp + extension)
        self.file_count += 1

        # COPY EXPORTED FILES
        copies = False
        name = __package__
        if name in context.preferences.addons:
            prefs = context.preferences.addons[name].preferences
            if prefs and hasattr(prefs, 'copy_on_export'):
                copies = prefs.copy_on_export

        if copies and settings.copy_on_export:
            exportfile = Path(fp).with_suffix(extension)
            if exportfile.exists():
                oldroot = Path(bpy.path.abspath(settings.directory))
                newroot = Path(bpy.path.abspath(settings.copy_directory))
                if not oldroot.resolve() == newroot.resolve():
                    subpath = exportfile.relative_to(oldroot)
                    copyfile = newroot / subpath

                    shutil.copy(exportfile, copyfile)
                    print('made this copy:   ', copyfile.resolve())
                    self.copy_count += 1

'''
# THIS IS A GREAT WAY FOR TEMPORARY VISIBILITY CHANGES FOR EXPORT
from contextlib import contextmanager
@contextmanager
def temporary_visibility(objects):
    """
    A context manager to temporarily make Blender objects and their entire
    parent hierarchies visible.

    When the 'with' block is exited, it automatically restores the original
    visibility states of all affected objects. This is useful for export
    operations where objects must be visible to be included.

    Args:
        objects (list): A list of Blender object references (e.g., from
                        bpy.context.selected_objects).
    
    Example Usage:
        # Select some objects in the 3D Viewport
        selected_objs = bpy.context.selected_objects
        
        with temporary_visibility(selected_objs):
            # Your export code goes here.
            # All selected objects and their parents are now visible.
            print("Exporting visible objects...")
            # bpy.ops.export_scene.fbx(filepath="path/to/export.fbx")
        
        # After this block, the original visibility is restored.
    """
    
    # Use a set for efficiency, as objects might share parents.
    originally_hidden = set()
    
    # Create a comprehensive set of all objects that need to be checked,
    # including the initial objects and all of their parents.
    all_objects_to_process = set(objects)
    for obj in objects:
        parent = obj.parent
        while parent:
            all_objects_to_process.add(parent)
            parent = parent.parent
            
    # First, identify all objects in the hierarchy that are currently hidden,
    # add them to our 'originally_hidden' set, and then make them visible.
    # The hide_get() method correctly checks the final evaluated visibility.
    for obj in all_objects_to_process:
        if obj.hide_get():
            originally_hidden.add(obj)
            obj.hide_set(False)
            
    print(f"Temporarily made {len(originally_hidden)} object(s) visible for the operation.")

    try:
        # 'yield' passes control back to the code inside the 'with' block.
        # The script will pause here until that block is finished or an error occurs.
        yield
    finally:
        # This code is guaranteed to run after the 'with' block.
        # It iterates through only the objects that we originally un-hid
        # and sets their visibility back to hidden.
        print("Restoring original visibility states...")
        for obj in originally_hidden:
            # A good practice is to check if the object still exists,
            # in case the operation inside the 'with' block deleted it.
            if obj.name in bpy.data.objects:
                obj.hide_set(True)
        print("Visibility restored.")
        
objects = bpy.context.collection.objects

with temporary_visibility(objects):
    for obj in objects:
        if obj.visible_get():
            print(f'{obj.name} is visible')

##########################################################################################################
##########################################################################################################
##########################################################################################################
##########################################################################################################
ENTIRE FILE BELOW RESTRUCTURED BY GEMINI
##########################################################################################################
##########################################################################################################
##########################################################################################################
##########################################################################################################

import bpy
import shutil
from pathlib import Path
from contextlib import contextmanager
from bpy.types import Operator

# Assuming 'utils' is a module in your addon for loading presets
# from . import utils

class EXPORT_MESH_OT_batch(Operator):
    """Export many objects to separate files all at once."""
    bl_idname = "export_mesh.batch"
    bl_label = "Batch Export"

    def execute(self, context):
        """
        Main entry point. Orchestrates the validation, job creation,
        and execution of the batch export process.
        """
        self.file_count = 0
        self.copy_count = 0
        settings = context.scene.batch_export

        # 1. Validate prerequisites (saved file, valid directory)
        error = self._validate_prerequisites(settings)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        base_dir = Path(bpy.path.abspath(settings.directory))

        # 2. Wrap the entire operation in a state preservation context manager
        with self._preserve_blender_state(context):
            
            # 3. Get a master list of objects to consider for export
            filtered_objects = self._get_filtered_objects(context, settings)
            if not filtered_objects:
                self.report({'WARNING'}, "No objects matched the filter settings.")
                return {'FINISHED'}

            # 4. Generate and process each export job based on the export mode
            try:
                export_jobs = self._generate_export_jobs(settings, filtered_objects, base_dir)
                for job in export_jobs:
                    self._process_export_job(context, settings, job)
            except Exception as e:
                self.report({'ERROR'}, f"Operation failed: {e}")
                # The 'finally' clause in the context managers will still clean up
                return {'CANCELLED'}

        # 5. Report the final results
        self._report_results(context, settings)
        return {'FINISHED'}

    # =================================================================
    # 1. VALIDATION AND SETUP
    # =================================================================

    def _validate_prerequisites(self, settings):
        """Checks for common issues before starting. Returns an error string or None."""
        base_dir = Path(settings.directory)
        if not base_dir.is_absolute() and not bpy.data.is_saved:
            return "Please save the .blend file before exporting with a relative path."
        
        abs_path = Path(bpy.path.abspath(settings.directory))
        if not abs_path.is_dir():
            return f"Export directory does not exist: {abs_path}"
        
        return None

    # =================================================================
    # 2. STATE MANAGEMENT (CONTEXT MANAGERS)
    # =================================================================

    @contextmanager
    def _preserve_blender_state(self, context):
        """Saves and restores selection, active object, and mode."""
        view_layer = context.view_layer
        original_selection = context.selected_objects[:]
        original_active = view_layer.objects.active
        original_mode = original_active.mode if original_active else 'OBJECT'

        try:
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            yield
        finally:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            view_layer.objects.active = original_active
            if original_active and original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)

    @contextmanager
    def temporary_visibility(self, objects):
        """Temporarily makes objects and their parent hierarchies visible for export."""
        originally_hidden = set()
        objects_to_process = set(objects)
        for obj in objects:
            parent = obj.parent
            while parent:
                objects_to_process.add(parent)
                parent = parent.parent
        
        for obj in objects_to_process:
            if obj.hide_get():
                originally_hidden.add(obj)
                obj.hide_set(False)
        try:
            yield
        finally:
            for obj in originally_hidden:
                if obj.name in bpy.data.objects:
                    obj.hide_set(True)

    @contextmanager
    def _temporary_transform(self, settings, objects_to_transform):
        """Applies and then resets object transforms for the duration of the export."""
        original_transforms = {
            obj: (obj.location.copy(), obj.rotation_euler.copy(), obj.scale.copy())
            for obj in objects_to_transform
        }
        
        try:
            for obj in objects_to_transform:
                is_child_of_selected = "PARENT" in settings.mode and obj.parent in objects_to_transform
                if not is_child_of_selected:
                    if settings.set_location: obj.location = settings.location
                    if settings.set_rotation: obj.rotation_euler = settings.rotation
                    if settings.set_scale: obj.scale = settings.scale
            yield
        finally:
            for obj, (loc, rot, scale) in original_transforms.items():
                if obj.name in bpy.data.objects:
                    obj.location, obj.rotation_euler, obj.scale = loc, rot, scale

    @contextmanager
    def _managed_lods(self, settings, obj):
        """Creates and cleans up LOD objects for FBX export."""
        if not (settings.create_lod and settings.file_format == 'FBX' and obj.type == 'MESH'):
            yield [obj]  # No LODs needed, just yield the original object
            return

        lod_objects = []
        original_name = obj.name
        try:
            # Prepare original object
            obj.name = f"{original_name}_preLOD"
            
            # Create LOD Parent (Empty)
            collection = obj.users_collection[0]
            lod_parent = bpy.data.objects.new(original_name, None)
            collection.objects.link(lod_parent)
            lod_parent.location = obj.location
            lod_parent.rotation_quaternion = obj.rotation_quaternion
            lod_parent["fbx_type"] = "LodGroup"
            if obj.parent:
                lod_parent.parent = obj.parent
            lod_objects.append(lod_parent)
            
            # Create LOD0 (base mesh)
            lod0 = obj.copy()
            lod0.data = lod0.data.copy()
            lod0.name = f"{original_name}_LOD0"
            lod0.parent = lod_parent
            lod0.location = (0, 0, 0)
            collection.objects.link(lod0)
            lod_objects.append(lod0)
            
            # Create subsequent LODs
            for i in range(settings.lod_count):
                lod = lod0.copy()
                lod.data = lod.data.copy()
                lod.name = f"{original_name}_LOD{i + 1}"
                lod.parent = lod_parent
                collection.objects.link(lod)
                mod = lod.modifiers.new(name='DecimateLOD', type='DECIMATE')
                mod.ratio = getattr(settings, f"lod{i + 1}_ratio")
                lod_objects.append(lod)
            
            yield lod_objects

        finally:
            # Guaranteed cleanup
            for lod_obj in lod_objects:
                bpy.data.objects.remove(lod_obj, do_unlink=True)
            if obj.name.endswith('_preLOD'):
                obj.name = original_name

    # =================================================================
    # 3. OBJECT GATHERING AND JOB CREATION
    # =================================================================

    def _get_filtered_objects(self, context, settings):
        """Gets a list of all objects that meet the initial filter criteria."""
        source_objects = []
        if settings.limit == 'SELECTED':
            source_objects = context.selected_objects[:]
        elif settings.limit == 'VISIBLE':
            source_objects = [obj for obj in context.view_layer.objects if obj.visible_get()]
        elif settings.limit == 'RENDERABLE':
            renderable_names = {obj.name for obj in self._get_all_renderable_objects(context.scene)}
            source_objects = [obj for obj in context.view_layer.objects if obj.name in renderable_names]
        else: # 'ALL'
            source_objects = context.scene.objects[:]
            
        # Further filter by object types
        return [obj for obj in source_objects if obj.type in settings.object_types]

    def _get_all_renderable_objects(self, scene):
        """Recursively finds all objects not hidden for rendering."""
        renderable = []
        def find_in_collection(collection):
            if collection.hide_render: return
            for obj in collection.objects:
                if not obj.hide_render:
                    renderable.append(obj)
            for child_coll in collection.children:
                find_in_collection(child_coll)
        find_in_collection(scene.collection)
        return renderable

    def _generate_export_jobs(self, settings, objects, base_dir):
        """A generator that yields a 'job' dictionary for each file to be exported."""
        mode = settings.mode
        
        if mode == 'OBJECTS' or 'COLLECTION_SUBDIR' in mode and 'PARENT' not in mode:
            for obj in objects:
                yield self._create_job(settings, obj.name, [obj], base_dir, source_obj=obj)

        elif mode == 'PARENT_OBJECTS' or 'COLLECTION_SUBDIR' in mode and 'PARENT' in mode:
            object_set = set(objects)
            for obj in objects:
                if obj.parent not in object_set:  # Only export top-level parents
                    children = [c for c in obj.children_recursive if c in object_set]
                    yield self._create_job(settings, obj.name, [obj] + children, base_dir, source_obj=obj)
        
        elif mode == 'COLLECTIONS':
            collections_to_export = {}
            for obj in objects:
                for coll in obj.users_collection:
                    collections_to_export.setdefault(coll, []).append(obj)
            for coll, coll_objects in collections_to_export.items():
                yield self._create_job(settings, coll.name, coll_objects, base_dir)
        
        elif mode == 'SCENE':
            filename = settings.prefix + settings.suffix
            if not filename:
                filename = Path(bpy.data.filepath).stem if bpy.data.is_saved else "Untitled"
            yield self._create_job(settings, filename, objects, base_dir)

    def _create_job(self, settings, name, objects, base_dir, source_obj=None):
        """Helper to build a job dictionary, handling subdirectories and prefixes."""
        job_dir = base_dir
        item_name = name
        
        # Handle collection subdirectories
        if 'COLLECTION_SUBDIR' in settings.mode and source_obj and source_obj.users_collection:
            collection = source_obj.users_collection[0]
            if collection.name != "Scene Collection":
                if settings.full_hierarchy:
                    # This assumes a 'utils.get_collection_hierarchy' function exists
                    hierarchy = utils.get_collection_hierarchy(collection.name)
                    job_dir = base_dir / hierarchy
                else:
                    job_dir = base_dir / collection.name
                job_dir.mkdir(parents=True, exist_ok=True)
        
        # Handle collection prefix
        if settings.prefix_collection and 'OBJECT' in settings.mode and source_obj and source_obj.users_collection:
            collection_name = source_obj.users_collection[0].name
            if collection_name != 'Scene Collection':
                item_name = f"{collection_name}_{item_name}"

        return {'name': item_name, 'objects': objects, 'directory': job_dir}

    # =================================================================
    # 4. CORE EXPORT PROCESSING
    # =================================================================

    def _process_export_job(self, context, settings, job):
        """Executes a single export job with robust state management."""
        if not job['objects']:
            return

        # Set selection for this job
        for obj in job['objects']:
            obj.select_set(True)
            
        # Use nested context managers for maximum safety
        try:
            with self.temporary_visibility(job['objects']):
                with self._temporary_transform(settings, context.selected_objects):
                    # LOD management is complex and destructive, so it gets its own manager.
                    # This handles the case where only one object gets LODs.
                    is_lod_job = settings.create_lod and settings.file_format == 'FBX'
                    if is_lod_job and len(job['objects']) == 1 and job['objects'][0].type == 'MESH':
                        with self._managed_lods(settings, job['objects'][0]) as lod_export_objects:
                            bpy.ops.object.select_all(action='DESELECT')
                            for obj in lod_export_objects: obj.select_set(True)
                            filepath = self._dispatch_export_operator(settings, job)
                    else:
                        filepath = self._dispatch_export_operator(settings, job)

                    if filepath:
                        self.file_count += 1
                        print(f"Exported: {filepath}")
                        self._copy_exported_file(settings, filepath)
        finally:
            # Deselect all after the job is done
            bpy.ops.object.select_all(action='DESELECT')

    def _dispatch_export_operator(self, settings, job):
        """Calls the appropriate Blender export operator based on settings."""
        prefix = settings.prefix
        suffix = settings.suffix
        clean_name = prefix + bpy.path.clean_name(job['name']) + suffix
        filepath_no_ext = job['directory'] / clean_name
        
        # This giant if/elif block could be a dictionary mapping formats to functions
        # but is kept this way for clarity and similarity to the original.
        ext = ""
        options = {}
        
        if settings.file_format == "FBX":
            ext = '.fbx'
            # options = utils.load_operator_preset('export_scene.fbx', settings.fbx_preset)
            options.update({
                "filepath": str(filepath_no_ext) + ext,
                "use_selection": True,
                "use_mesh_modifiers": settings.apply_mods
            })
            bpy.ops.export_scene.fbx(**options)
        
        elif settings.file_format == "glTF":
            ext = '.glb'
            # options = utils.load_operator_preset('export_scene.gltf', settings.gltf_preset)
            options.update({
                "filepath": str(filepath_no_ext),
                "use_selection": True,
                "export_apply": settings.apply_mods
            })
            bpy.ops.export_scene.gltf(**options)
            
        # ... Add other file formats (OBJ, USD, ABC, etc.) here in the same pattern ...
        
        else:
            return None # Unsupported format
            
        return filepath_no_ext.with_suffix(ext)

    # =================================================================
    # 5. POST-PROCESSING AND REPORTING
    # =================================================================

    def _copy_exported_file(self, settings, exported_file_path):
        """Copies the exported file to a secondary directory if enabled."""
        prefs = bpy.context.preferences.addons[__package__].preferences
        should_copy = prefs.copy_on_export and settings.copy_on_export
        
        if not should_copy or not exported_file_path.exists():
            return
            
        try:
            source_root = Path(bpy.path.abspath(settings.directory)).resolve()
            dest_root = Path(bpy.path.abspath(settings.copy_directory)).resolve()
            
            if source_root != dest_root:
                relative_path = exported_file_path.relative_to(source_root)
                copy_path = dest_root / relative_path
                copy_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(exported_file_path, copy_path)
                self.copy_count += 1
                print(f"Copied to: {copy_path}")
        except Exception as e:
            print(f"Could not copy file: {e}")

    def _report_results(self, context, settings):
        """Generates the final report message for the user."""
        prefs = context.preferences.addons[__package__].preferences
        copies_enabled = prefs.copy_on_export and settings.copy_on_export

        if self.file_count == 0:
            self.report({'INFO'}, "Operation complete. No files were exported.")
        elif copies_enabled and self.copy_count > 0:
            self.report({'INFO'}, f"Exported {self.file_count} file(s) and made {self.copy_count} copies.")
        else:
            self.report({'INFO'}, f"Successfully exported {self.file_count} file(s).")


'''

registry = [
    EXPORT_MESH_OT_batch,
]