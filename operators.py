
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

# 1. Get Project Directory from Preferences
        name = __package__
        pref_project_dir = ""
        if name in context.preferences.addons:
            prefs = context.preferences.addons[name].preferences
            if prefs and hasattr(prefs, 'project_dir'):
                pref_project_dir = prefs.project_dir

        # 2. Calculate Base Directory
        if pref_project_dir:
            # If Project Dir is set, it overrides the .blend file as the relative root
            raw_dir = settings.directory
            # Strip Blender's relative prefix '//' if present so it doesn't conflict
            if raw_dir.startswith('//'):
                 raw_dir = raw_dir[2:]
            
            # Combine Project Dir with Output Dir. 
            # If Output Dir is absolute (e.g. "C:\"), it will correctly override the join.
            base_dir = os.path.join(bpy.path.abspath(pref_project_dir), raw_dir)
            base_dir = os.path.normpath(base_dir)
            
        else:
            # Standard Blender behavior (relative to .blend file)
            base_dir = settings.directory
            if not bpy.data.is_saved:
                # If unsaved, we cannot use relative paths starting with //
                if base_dir.startswith("//"):
                    self.report(
                        {'ERROR'}, "Save .blend file before exporting to relative directory\n(or set a Project Directory in Preferences)")
                    return {'FINISHED'}
            base_dir = bpy.path.abspath(base_dir)

        # 3. Validate existence
        if not os.path.isdir(base_dir):
            msg = f"Export directory doesn't exist:\n{base_dir}"
            self.report({'ERROR'}, msg)
            print(msg) # Print to console for easier debugging of paths
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

        # Final File Name
        prefix = settings.prefix
        # Check Prefix for Subdirectories
        prefixroot = os.path.dirname( os.path.join(base_dir, prefix) )
        if not os.path.exists(prefixroot):
            try:
                os.makedirs(prefixroot)
                print(f"Directory created: {prefixroot}")
            except OSError as e:
                self.report({'ERROR'}, f"Error creating directory {prefixroot}: {e}")
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
##########################################################################################################
##########################################################################################################
ENTIRE EXPORT OPERATOR RESTRUCTURED BY GEMINI (UPDATED WITH PROJECT_DIR)
##########################################################################################################
##########################################################################################################

import bpy
import shutil
from pathlib import Path
from contextlib import contextmanager
from bpy.types import Operator
from . import utils

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
        prefs = context.preferences.addons[__package__].preferences

        # 1. Resolve Base Directory
        # Determines the absolute root path for exports based on preferences.
        try:
            base_dir = self._resolve_base_dir(settings, prefs)
        except ValueError as e:
             self.report({'ERROR'}, str(e))
             return {'CANCELLED'}

        # 2. Validate prerequisites (directory existence)
        if not base_dir.is_dir():
             self.report({'ERROR'}, f"Export directory does not exist: {base_dir}")
             return {'CANCELLED'}

        # 3. Wrap the entire operation in a state preservation context manager
        with self._preserve_blender_state(context):
            
            # 4. Get a master list of objects to consider for export
            filtered_objects = self._get_filtered_objects(context, settings)
            if not filtered_objects:
                self.report({'WARNING'}, "No objects matched the filter settings.")
                return {'FINISHED'}

            # 5. Generate and process each export job based on the export mode
            try:
                # We pass the resolved base_dir to the job generator
                export_jobs = self._generate_export_jobs(settings, filtered_objects, base_dir)
                for job in export_jobs:
                    self._process_export_job(context, settings, job)
            except Exception as e:
                self.report({'ERROR'}, f"Operation failed: {e}")
                import traceback
                traceback.print_exc() # Print full error to console for debugging
                return {'CANCELLED'}

        # 6. Report the final results
        self._report_results(context, settings)
        return {'FINISHED'}

    # =================================================================
    # 1. VALIDATION AND SETUP
    # =================================================================

    def _resolve_base_dir(self, settings, prefs):
        """
        Calculates the absolute base directory. 
        Raises ValueError if the path cannot be resolved (e.g. unsaved blend file with relative path).
        """
        project_dir_raw = getattr(prefs, 'project_dir', '')
        
        if project_dir_raw:
             # If Project Directory is set, it takes precedence as the root.
             # We treat the settings.directory as relative to this project root.
             project_root = Path(bpy.path.abspath(project_dir_raw))
             
             relative_part = settings.directory
             # Remove Blender's relative prefix '//' if present so pathlib joins correctly
             if relative_part.startswith('//'):
                  relative_part = relative_part[2:]
             elif relative_part.startswith('\\'):
                  relative_part = relative_part[1:]

             return (project_root / relative_part).resolve()
        else:
             # Standard behavior: relative to .blend file
             if settings.directory.startswith('//') and not bpy.data.is_saved:
                  raise ValueError("Save the .blend file before exporting to a relative directory, or set a Project Directory in preferences.")
             
             return Path(bpy.path.abspath(settings.directory)).resolve()

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
            # This finally block ensures cleanup happens even if an error occurs during export
            if context.view_layer.objects.active and context.view_layer.objects.active.mode != 'OBJECT':
                 bpy.ops.object.mode_set(mode='OBJECT')

            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                try:
                    obj.select_set(True)
                except RuntimeError:
                     pass # Object might have been deleted during process
                     
            if original_active and original_active.name in context.view_layer.objects:
                view_layer.objects.active = original_active
                if original_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=original_mode)

    @contextmanager
    def temporary_visibility(self, objects):
        """Temporarily makes objects and their parent hierarchies visible for export."""
        originally_hidden = set()
        objects_to_process = set(objects)
        # Ensure parents are also visible so children can be exported correctly
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
                 # Check if object still exists before trying to hide it
                if obj and obj.name in bpy.data.objects:
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
                # Don't apply transforms to children if we are exporting PARENT_OBJECTS,
                # otherwise double-transforms might occur depending on exporter settings.
                is_child_of_selected = "PARENT" in settings.mode and obj.parent in objects_to_transform
                if not is_child_of_selected:
                    if settings.set_location: obj.location = settings.location
                    if settings.set_rotation: obj.rotation_euler = settings.rotation
                    if settings.set_scale: obj.scale = settings.scale
            yield
        finally:
            for obj, (loc, rot, scale) in original_transforms.items():
                if obj and obj.name in bpy.data.objects:
                    obj.location, obj.rotation_euler, obj.scale = loc, rot, scale

    @contextmanager
    def _managed_lods(self, settings, obj):
        """Creates and cleans up LOD objects for FBX export."""
        # Exit early if not applicable
        if not (settings.create_lod and settings.file_format == 'FBX' and obj.type == 'MESH'):
            yield [obj]
            return

        lod_objects = []
        original_name = obj.name
        original_parent = obj.parent
        
        try:
            # 1. Rename original to prevent name collisions and indicate it's NOT the export target
            obj.name = f"{original_name}_preLOD"
            
            # 2. Create LOD Group Parent (Empty)
            # We link it to the same collection as the source object
            collection = obj.users_collection[0]
            lod_parent = bpy.data.objects.new(original_name, None)
            collection.objects.link(lod_parent)
            
            # Match transforms of original
            lod_parent.location = obj.location
            lod_parent.rotation_quaternion = obj.rotation_quaternion
            lod_parent.rotation_euler = obj.rotation_euler
            lod_parent.scale = obj.scale
            
            # FBX specific custom property for recognized LODs
            lod_parent["fbx_type"] = "LodGroup"
            if original_parent:
                lod_parent.parent = original_parent
                
            lod_objects.append(lod_parent)
            
            # 3. Create LOD0 (The active mesh, parented to the LOD group)
            lod0 = obj.copy()
            lod0.data = lod0.data.copy() # Deep copy data to avoid modifying original mesh
            lod0.name = f"{original_name}_LOD0"
            collection.objects.link(lod0)
            
            # Parent to LOD group and zero out local transforms
            lod0.parent = lod_parent
            lod0.matrix_local.identity() 
            
            lod_objects.append(lod0)
            
            # 4. Create subsequent generated LODs
            for i in range(settings.lod_count):
                lod_ratio = getattr(settings, f"lod{i + 1}_ratio")
                # Skip if ratio is 1.0 (no reduction needed, saves processing)
                if lod_ratio >= 1.0: continue

                lod = lod0.copy()
                lod.data = lod.data.copy()
                lod.name = f"{original_name}_LOD{i + 1}"
                collection.objects.link(lod)
                lod.parent = lod_parent
                lod.matrix_local.identity()
                
                mod = lod.modifiers.new(name='DecimateLOD', type='DECIMATE')
                mod.ratio = lod_ratio
                lod_objects.append(lod)
            
            yield lod_objects

        finally:
            # Guaranteed cleanup of temporary objects
            for lod_obj in lod_objects:
                if lod_obj and lod_obj.name in bpy.data.objects:
                    bpy.data.objects.remove(lod_obj, do_unlink=True)
            
            # Restore original object name
            if obj and obj.name.endswith('_preLOD'):
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
            # Get all objects that will actually render
            renderable_names = {obj.name for obj in self._get_all_renderable_objects(context.scene)}
            source_objects = [obj for obj in context.view_layer.objects if obj.name in renderable_names]
        else: # 'ALL' in view layer
             # Using view_layer.objects instead of scene.objects ensures we only get objects
             # currently instantiated in this view layer (relevant for complex scenes)
            source_objects = context.view_layer.objects[:]
            
        # Further filter by object types specified in settings
        return [obj for obj in source_objects if obj.type in settings.object_types]

    def _get_all_renderable_objects(self, scene):
        """
        Recursively finds all objects that are NOT hidden from render.
        Handles complex collection visibility hierarchies.
        """
        renderable = []
        # We temporarily make everything visible in viewport to accurately check
        # 'hide_render' status if it relies on drivers or complex states,
        # though usually hide_render is independent.
        # The safer approach is just recursive checking without forcing viewport vis:
        
        def is_collection_renderable(col):
             if col.hide_render: return False
             # Recurse up to ensure no parent collection is hidden
             # (Blender doesn't always strictly enforce this in standard API but good practice)
             return True

        def check_collection(collection):
            if collection.hide_render: return
            
            for obj in collection.objects:
                if not obj.hide_render:
                    renderable.append(obj)
            
            for child in collection.children:
                check_collection(child)

        check_collection(scene.collection)
        return renderable

    def _generate_export_jobs(self, settings, objects, base_dir):
        """A generator that yields a 'job' dictionary for each file to be exported."""
        mode = settings.mode
        
        if mode == 'OBJECTS' or ('COLLECTION_SUBDIR' in mode and 'PARENT' not in mode):
            for obj in objects:
                yield self._create_job(settings, obj.name, [obj], base_dir, source_obj=obj)

        elif mode == 'PARENT_OBJECTS' or ('COLLECTION_SUBDIR' in mode and 'PARENT' in mode):
            # Convert to set for fast lookups
            object_set = set(objects)
            for obj in objects:
                # If this object's parent is ALSO in the selection list, skip it.
                # We only want to generate jobs for the top-most parents in the selection.
                if obj.parent in object_set:
                     continue

                # Gather all descendents that are also in the filter list
                # (children_recursive gives all nested children)
                children_to_export = [c for c in obj.children_recursive if c in object_set]
                yield self._create_job(settings, obj.name, [obj] + children_to_export, base_dir, source_obj=obj)
        
        elif mode == 'COLLECTIONS':
            # Group objects by their primary collection
            collections_to_export = {}
            for obj in objects:
                if obj.users_collection:
                    # Objects can be in multiple collections; we take the first one as primary
                    primary_coll = obj.users_collection[0]
                    collections_to_export.setdefault(primary_coll, []).append(obj)
            
            for coll, coll_objects in collections_to_export.items():
                yield self._create_job(settings, coll.name, coll_objects, base_dir)
        
        elif mode == 'SCENE':
            filename = settings.prefix + settings.suffix
            # If no prefix/suffix, fallback to blend file name
            if not filename:
                filename = Path(bpy.data.filepath).stem if bpy.data.is_saved else "Untitled"
            yield self._create_job(settings, filename, objects, base_dir)

    def _create_job(self, settings, name, objects, base_dir, source_obj=None):
        """Helper to build a job dictionary, handling subdirectories and prefixes."""
        job_dir = base_dir
        item_name = name
        
        # Handle collection subdirectories if enabled
        if 'COLLECTION_SUBDIR' in settings.mode and source_obj and source_obj.users_collection:
            collection = source_obj.users_collection[0]
            if collection.name != "Scene Collection":
                if settings.full_hierarchy:
                    # This assumes 'utils.get_collection_hierarchy' exists as in original code
                    hierarchy = utils.get_collection_hierarchy(collection.name)
                    job_dir = base_dir / hierarchy
                else:
                    job_dir = base_dir / collection.name
                
                # Create the subdirectory immediately so it exists for export
                job_dir.mkdir(parents=True, exist_ok=True)
        
        # Handle collection prefixing if enabled
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

        # Deselect everything first to ensure clean state for this job
        bpy.ops.object.select_all(action='DESELECT')

        # Use nested context managers for maximum safety during temporary changes
        try:
            # 1. Ensure objects are visible (needed for some exporters)
            with self.temporary_visibility(job['objects']):
                 # 2. Apply temporary transforms (Location/Rotation/Scale overrides)
                with self._temporary_transform(settings, job['objects']):
                    
                    objects_to_export = job['objects']
                    
                    # 3. Handle LOD generation (specifically for single mesh FBX exports)
                    is_lod_job = settings.create_lod and settings.file_format == 'FBX'
                    single_mesh = len(job['objects']) == 1 and job['objects'][0].type == 'MESH'
                    
                    if is_lod_job and single_mesh:
                        # _managed_lods yields the new temporary LOD objects
                        with self._managed_lods(settings, job['objects'][0]) as lod_objects:
                            self._select_and_export(settings, job, lod_objects)
                    else:
                        self._select_and_export(settings, job, objects_to_export)

        finally:
            # Ensure everything is deselected after the job completes
            bpy.ops.object.select_all(action='DESELECT')

    def _select_and_export(self, settings, job, objects_to_export):
        """Helper to select the specific objects for this job and trigger export."""
        # Select only the objects for this specific job
        for obj in objects_to_export:
            if obj and obj.name in bpy.data.objects:
                 obj.select_set(True)
        
        # Run the actual Blender operator
        filepath = self._dispatch_export_operator(settings, job)

        if filepath:
            self.file_count += 1
            print(f"Exported: {filepath}")
            # Perform the optional copy
            self._copy_exported_file(settings, filepath)

    def _dispatch_export_operator(self, settings, job):
        """Calls the appropriate Blender export operator based on settings."""
        prefix = settings.prefix
        suffix = settings.suffix
        # Clean the name to ensure it's valid for a file system
        clean_name = prefix + bpy.path.clean_name(job['name']) + suffix
        filepath_no_ext = job['directory'] / clean_name
        
        # Map format enums to their handler functions
        DISPATCHER = {
            "FBX": self.export_fbx,
            "glTF": self.export_gltf,
            "ABC": self.export_alembic,
            "USD": self.export_usd,
            "SVG": self.export_svg,
            "PDF": self.export_pdf,
            "OBJ": self.export_obj,
            "PLY": self.export_ply,
            "STL": self.export_stl,
        }

        handler = DISPATCHER.get(settings.file_format)
        if handler:
             # Execute the specific export function
             return handler(settings, str(filepath_no_ext))
        return None

    # =================================================================
    # 5. POST-PROCESSING AND REPORTING
    # =================================================================

    def _copy_exported_file(self, settings, exported_file_path):
        """Copies the exported file to a secondary directory if enabled."""
        # Re-read prefs to ensure we have latest state
        prefs = bpy.context.preferences.addons[__package__].preferences
        should_copy = prefs.copy_on_export and settings.copy_on_export
        
        if not should_copy: return

        exported_path = Path(exported_file_path)
        if not exported_path.exists(): return
            
        try:
            # Calculate the relative path from the main export root
            # This maintains subdirectory structures in the copy location
            main_export_root = self._resolve_base_dir(settings, prefs)
            
            try:
                relative_path = exported_path.relative_to(main_export_root)
            except ValueError:
                # Fallback if it wasn't relative for some reason, just use filename
                relative_path = exported_path.name

            dest_root = Path(bpy.path.abspath(settings.copy_directory)).resolve()
            copy_path = dest_root / relative_path
            
            # Ensure destination subdirectory exists
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy(exported_path, copy_path)
            self.copy_count += 1
            print(f"Copied to: {copy_path}")
        except Exception as e:
            print(f"Copy failed: {e}")

    def _report_results(self, context, settings):
        """Generates the final report message for the user."""
        prefs = context.preferences.addons[__package__].preferences
        copies_enabled = prefs.copy_on_export and settings.copy_on_export

        if self.file_count == 0:
            self.report({'WARNING'}, "Operation complete. No files were exported.")
        elif copies_enabled and self.copy_count > 0:
            self.report({'INFO'}, f"Exported {self.file_count} file(s) and made {self.copy_count} copies.")
        else:
            self.report({'INFO'}, f"Successfully exported {self.file_count} file(s).")


    # --- Individual Export Wrappers ---
    # These standardize calling the various Blender operators.
    # They return the final full filepath (with extension) on success.

    def export_fbx(self, settings, filepath_no_ext):
        ext = '.fbx'
        full_path = filepath_no_ext + ext
        options = utils.load_operator_preset('export_scene.fbx', settings.fbx_preset)
        options.update({
            "filepath": full_path,
            "use_selection": True,
            "use_mesh_modifiers": settings.apply_mods
        })
        bpy.ops.export_scene.fbx(**options)
        return full_path
    
    def export_gltf(self, settings, filepath_no_ext):
        # glTF exporter automatically adds extension based on format if not present,
        # but safer to be explicit if we know we want GLB.
        ext = '.glb' 
        full_path = filepath_no_ext + ext
        options = utils.load_operator_preset('export_scene.gltf', settings.gltf_preset)
        options.update({
            "filepath": full_path,
            "export_format": 'GLB', # Forcing GLB as standard, could be made an option
            "use_selection": True,
            "export_apply": settings.apply_mods
        })
        bpy.ops.export_scene.gltf(**options)
        return full_path
        
    def export_alembic(self, settings, filepath_no_ext):
        ext = '.abc'
        full_path = filepath_no_ext + ext
        options = utils.load_operator_preset('wm.alembic_export', settings.abc_preset)
        options.update({
            "filepath": full_path,
            "selected": True,
            "start": settings.frame_start,
            "end": settings.frame_end
        })
        bpy.ops.wm.alembic_export('EXEC_DEFAULT', **options)
        return full_path
    
    def export_usd(self, settings, filepath_no_ext):
        ext = settings.usd_format
        full_path = filepath_no_ext + ext
        options = utils.load_operator_preset('wm.usd_export', settings.usd_preset)
        options.update({
            "filepath": full_path,
            "selected_objects_only": True
        })
        bpy.ops.wm.usd_export(**options)
        return full_path
    
    def export_svg(self, settings, filepath_no_ext):
        ext = '.svg'
        full_path = filepath_no_ext + ext
        bpy.ops.wm.gpencil_export_svg(filepath=full_path, selected_object_type='SELECTED')
        return full_path
    
    def export_pdf(self, settings, filepath_no_ext):
        ext = '.pdf'
        full_path = filepath_no_ext + ext
        bpy.ops.wm.gpencil_export_pdf(filepath=full_path, selected_object_type='SELECTED')
        return full_path
    
    def export_obj(self, settings, filepath_no_ext):
        ext = '.obj'
        full_path = filepath_no_ext + ext
        options = utils.load_operator_preset('wm.obj_export', settings.obj_preset)
        options.update({
            "filepath": full_path,
            "export_selected_objects": True,
            "apply_modifiers": settings.apply_mods
        })
        bpy.ops.wm.obj_export(**options)
        return full_path
    
    def export_ply(self, settings, filepath_no_ext):
        ext = '.ply'
        full_path = filepath_no_ext + ext
        bpy.ops.wm.ply_export(
            filepath=full_path, 
            ascii_format=settings.ply_ascii, 
            export_selected_objects=True, 
            apply_modifiers=settings.apply_mods
        )
        return full_path
    
    def export_stl(self, settings, filepath_no_ext):
        ext = '.stl'
        full_path = filepath_no_ext + ext
        bpy.ops.wm.stl_export(
            filepath=full_path, 
            ascii_format=settings.stl_ascii, 
            export_selected_objects=True, 
            apply_modifiers=settings.apply_mods
        )
        return full_path
'''

registry = [
    EXPORT_MESH_OT_batch,
]