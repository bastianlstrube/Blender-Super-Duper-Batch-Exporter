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
        Main entry point. Orchestrates validation, job creation,
        and execution of the batch export process.
        """
        self.file_count = 0
        self.copy_count = 0
        self.skipped_lods = []
        settings = context.scene.batch_export
        prefs = context.preferences.addons[__package__].preferences

        # 1. Resolve base directory
        try:
            base_dir = self._resolve_base_dir(settings, prefs)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        # 2. Validate that the directory actually exists
        if not base_dir.is_dir():
            self.report({'ERROR'}, f"Export directory does not exist:\n{base_dir}")
            return {'CANCELLED'}

        # 3. Get the master list of objects to consider
        filtered_objects = self._get_filtered_objects(context, settings)
        if not filtered_objects:
            self.report({'WARNING'}, "No objects matched the filter settings.")
            return {'FINISHED'}

        # 4. Run the entire export inside a state-preservation context manager
        with self._preserve_blender_state(context):

            # 5. Generate and process each export job
            try:
                for job in self._generate_export_jobs(settings, filtered_objects, base_dir):
                    self._process_export_job(context, settings, job)
            except Exception as e:
                self.report({'ERROR'}, f"Operation failed: {e}")
                import traceback
                traceback.print_exc()
                return {'CANCELLED'}

        # 6. Report final results
        self._report_results(context, settings)
        return {'FINISHED'}

    # =================================================================
    # 1. VALIDATION AND SETUP
    # =================================================================

    def _resolve_base_dir(self, settings, prefs):
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
        else:
            # Standard Blender behaviour: relative to the .blend file.
            if settings.directory.startswith('//') and not bpy.data.is_saved:
                raise ValueError(
                    "Save the .blend file before exporting to a relative directory,\n"
                    "or set a Project Directory in Preferences."
                )
            return Path(bpy.path.abspath(settings.directory)).resolve()

    # =================================================================
    # 2. STATE MANAGEMENT (CONTEXT MANAGERS)
    # =================================================================

    @contextmanager
    def _preserve_blender_state(self, context):
        """Saves and restores selection, active object, and interaction mode."""
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
                try:
                    if obj.name in context.view_layer.objects:
                        obj.select_set(True)
                except RuntimeError:
                    pass

            if original_active and original_active.name in context.view_layer.objects:
                view_layer.objects.active = original_active

                if original_mode != 'OBJECT':
                    is_editable = (
                        not original_active.library
                        and not (
                            original_active.override_library
                            and original_active.override_library.is_system_override
                        )
                    )
                    if is_editable:
                        try:
                            bpy.ops.object.mode_set(mode=original_mode)
                        except RuntimeError:
                            pass

    @contextmanager
    def _temporary_visibility(self, objects):
        """Temporarily makes objects (and their parents) visible for export."""
        objects_to_process = set(objects)
        for obj in objects:
            parent = obj.parent
            while parent:
                objects_to_process.add(parent)
                parent = parent.parent

        originally_hidden = {obj for obj in objects_to_process if obj.hide_get()}
        for obj in originally_hidden:
            obj.hide_set(False)
        try:
            yield
        finally:
            for obj in originally_hidden:
                if obj and obj.name in bpy.data.objects:
                    obj.hide_set(True)

    @contextmanager
    def _temporary_transform(self, settings, objects_to_transform):
        """Applies and then restores object transforms around an export."""
        original_transforms = {
            obj: (obj.location.copy(), obj.rotation_euler.copy(), obj.scale.copy())
            for obj in objects_to_transform
        }
        try:
            for obj in objects_to_transform:
                # Don't override a child's transform when its parent is also being exported.
                if obj.parent in objects_to_transform:
                    continue
                if settings.set_location:
                    obj.location = settings.location
                if settings.set_rotation:
                    obj.rotation_euler = settings.rotation
                if settings.set_scale:
                    obj.scale = settings.scale
            yield
        finally:
            for obj, (loc, rot, scale) in original_transforms.items():
                if obj and obj.name in bpy.data.objects:
                    obj.location = loc
                    obj.rotation_euler = rot
                    obj.scale = scale

    @contextmanager
    def _managed_lods(self, settings, obj):
        """
        Creates temporary LOD hierarchy objects for FBX export and guarantees
        their removal afterwards, even if an exception occurs.
        Yields the list of objects that should be selected for export.
        """
        is_editable = (
            not obj.library
            and not (
                obj.override_library
                and obj.override_library.is_system_override
            )
        )

        wants_lods = settings.create_lod and settings.file_format == 'FBX' and obj.type == 'MESH'

        # If they want LODs but the object is linked, warn the user and just export the base mesh.
        if wants_lods and not is_editable:
            self.skipped_lods.append(obj.name)
            self.report({'WARNING'}, f"Skipped LODs for '{obj.name}' (Linked Object, cannot edit). Exporting base mesh only.")
            yield [obj]
            return

        # If they don't want LODs, or it's the wrong format/type, just export normally.
        if not wants_lods:
            yield [obj]
            return

        lod_objects = []
        original_name = obj.name
        original_parent = obj.parent
        collection = obj.users_collection[0]

        try:
            # Rename original so it won't conflict with the new LOD parent name.
            obj.name = f"{original_name}_preLOD"

            # LOD group parent (empty)
            lod_parent = bpy.data.objects.new(original_name, None)
            collection.objects.link(lod_parent)
            lod_parent.location = obj.location
            lod_parent.rotation_euler = obj.rotation_euler
            lod_parent.rotation_quaternion = obj.rotation_quaternion
            lod_parent.scale = obj.scale
            lod_parent["fbx_type"] = "LodGroup"
            if original_parent:
                lod_parent.parent = original_parent
            lod_objects.append(lod_parent)

            # LOD0 — full-resolution copy
            lod0 = obj.copy()
            lod0.data = lod0.data.copy()
            lod0.name = f"{original_name}_LOD0"
            collection.objects.link(lod0)
            lod0.parent = lod_parent
            lod0.matrix_local.identity()
            lod_objects.append(lod0)

            # Additional decimated LODs
            for i in range(settings.lod_count):
                lod_ratio = getattr(settings, f"lod{i + 1}_ratio")
                if lod_ratio >= 1.0:
                    continue  # No reduction needed for this level
                lod = lod0.copy()
                lod.data = lod0.data.copy()
                lod.name = f"{original_name}_LOD{i + 1}"
                collection.objects.link(lod)
                lod.parent = lod_parent
                lod.matrix_local.identity()
                mod = lod.modifiers.new(name='DecimateLOD', type='DECIMATE')
                mod.ratio = lod_ratio
                lod_objects.append(lod)

            # Ensure modifiers are applied during export
            settings.apply_mods = True

            yield lod_objects

        finally:
            for lod_obj in lod_objects:
                if lod_obj and lod_obj.name in bpy.data.objects:
                    bpy.data.objects.remove(lod_obj, do_unlink=True)
            # Restore original name
            if obj and obj.name.endswith('_preLOD'):
                obj.name = original_name

    # =================================================================
    # 3. OBJECT GATHERING AND JOB CREATION
    # =================================================================

    def _get_filtered_objects(self, context, settings):
        """Returns all view-layer objects that pass the limit and type filters."""
        limit = settings.limit

        if limit == 'SELECTED':
            source = context.selected_objects[:]
        elif limit == 'VISIBLE':
            source = [obj for obj in context.view_layer.objects if obj.visible_get()]
        elif limit == 'RENDERABLE':
            renderable_names = {obj.name for obj in self._get_renderable_objects(context.scene)}
            source = [obj for obj in context.view_layer.objects if obj.name in renderable_names]
        else:  # 'ALL'
            source = list(context.view_layer.objects)

        return [obj for obj in source if obj.type in settings.object_types]

    def _get_renderable_objects(self, scene):
        """Recursively collects all objects not hidden from render."""
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

    def _generate_export_jobs(self, settings, objects, base_dir):
        """
        Generator that yields a job dict for each file to be exported.
        Each job contains: name, objects (list), directory (Path).
        """
        mode = settings.mode
        object_set = set(objects)

        if mode == 'OBJECTS':
            for obj in objects:
                yield self._build_job(settings, obj.name, [obj], base_dir, source_obj=obj)

        elif mode == 'PARENT_OBJECTS':
            for obj in objects:
                if obj.parent in object_set:
                    continue  # Will be included when its parent is processed
                children = [c for c in obj.children_recursive if c in object_set]
                yield self._build_job(settings, obj.name, [obj] + children, base_dir, source_obj=obj)

        elif mode == 'COLLECTIONS':
            collections_map = {}
            for obj in objects:
                if obj.users_collection:
                    primary = obj.users_collection[0]
                    collections_map.setdefault(primary, []).append(obj)
            for coll, coll_objects in collections_map.items():
                yield self._build_job(settings, coll.name, coll_objects, base_dir)

        elif mode == 'COLLECTION_SUBDIRECTORIES':
            for obj in objects:
                yield self._build_job(settings, obj.name, [obj], base_dir, source_obj=obj)

        elif mode == 'COLLECTION_SUBDIR_PARENTS':
            for obj in objects:
                if obj.parent in object_set:
                    continue
                children = [c for c in obj.children_recursive if c in object_set]
                yield self._build_job(settings, obj.name, [obj] + children, base_dir, source_obj=obj)

        elif mode == 'SCENE':
            prefix = settings.prefix
            suffix = settings.suffix
            if prefix or suffix:
                filename = prefix + suffix
            else:
                filename = Path(bpy.data.filepath).stem if bpy.data.is_saved else "Untitled"
            yield self._build_job(settings, filename, objects, base_dir)

    def _build_job(self, settings, name, objects, base_dir, source_obj=None):
        """
        Builds a single job dictionary, resolving any subdirectory and
        collection-prefix logic based on the current export mode.
        """
        job_dir = base_dir
        item_name = name

        # Resolve collection subdirectory if the mode calls for it
        if 'COLLECTION_SUBDIR' in settings.mode and source_obj and source_obj.users_collection:
            collection = source_obj.users_collection[0]
            if collection.name != "Scene Collection":
                if settings.full_hierarchy:
                    hierarchy = utils.get_collection_hierarchy(collection.name)
                    job_dir = base_dir / hierarchy
                else:
                    job_dir = base_dir / collection.name
                job_dir.mkdir(parents=True, exist_ok=True)

        # Prepend collection name to the file stem if enabled for OBJECTS mode
        if settings.prefix_collection and 'OBJECT' in settings.mode and source_obj and source_obj.users_collection:
            collection_name = source_obj.users_collection[0].name
            if collection_name != 'Scene Collection':
                item_name = f"{collection_name}_{item_name}"

        return {'name': item_name, 'objects': objects, 'directory': job_dir}

    # =================================================================
    # 4. CORE EXPORT PROCESSING
    # =================================================================

    def _process_export_job(self, context, settings, job):
        """Executes a single export job with full state management."""
        if not job['objects']:
            return

        bpy.ops.object.select_all(action='DESELECT')

        try:
            with self._temporary_visibility(job['objects']):
                with self._temporary_transform(settings, job['objects']):

                    is_lod_job = (
                        settings.create_lod
                        and settings.file_format == 'FBX'
                        and len(job['objects']) == 1
                        and job['objects'][0].type == 'MESH'
                    )

                    if is_lod_job:
                        with self._managed_lods(settings, job['objects'][0]) as lod_objects:
                            self._select_and_export(settings, job, lod_objects)
                    else:
                        self._select_and_export(settings, job, job['objects'])
        finally:
            bpy.ops.object.select_all(action='DESELECT')

    def _select_and_export(self, settings, job, objects_to_export):
        """Selects the given objects and dispatches the appropriate export operator."""
        for obj in objects_to_export:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)

        filepath = self._dispatch_export(settings, job)

        if filepath:
            self.file_count += 1
            print(f"Exported: {filepath}")
            self._copy_exported_file(settings, filepath)

    def _dispatch_export(self, settings, job):
        """
        Builds the output filepath and calls the correct Blender export operator.
        Returns the full filepath string on success, or None.
        """
        prefix = settings.prefix
        suffix = settings.suffix
        clean_name = prefix + bpy.path.clean_name(job['name']) + suffix

        # Ensure any prefix subdirectory exists
        fp_no_ext = job['directory'] / clean_name
        fp_no_ext.parent.mkdir(parents=True, exist_ok=True)

        fmt = settings.file_format

        if fmt == 'FBX':
            return self._export_fbx(settings, fp_no_ext)
        elif fmt == 'glTF':
            return self._export_gltf(settings, fp_no_ext)
        elif fmt == 'ABC':
            return self._export_alembic(settings, fp_no_ext)
        elif fmt == 'USD':
            return self._export_usd(settings, fp_no_ext)
        elif fmt == 'OBJ':
            return self._export_obj(settings, fp_no_ext)
        elif fmt == 'PLY':
            return self._export_ply(settings, fp_no_ext)
        elif fmt == 'STL':
            return self._export_stl(settings, fp_no_ext)
        elif fmt == 'SVG':
            return self._export_svg(settings, fp_no_ext)
        elif fmt == 'PDF':
            return self._export_pdf(settings, fp_no_ext)

        return None

    # =================================================================
    # 5. POST-PROCESSING AND REPORTING
    # =================================================================

    def _copy_exported_file(self, settings, exported_file_path):
        """Copies the exported file to the secondary copy directory if enabled."""
        prefs = bpy.context.preferences.addons[__package__].preferences
        if not (prefs.copy_on_export and settings.copy_on_export):
            return

        exported_path = Path(exported_file_path)
        if not exported_path.exists():
            return

        try:
            main_export_root = self._resolve_base_dir(settings, prefs)
            try:
                relative_path = exported_path.relative_to(main_export_root)
            except ValueError:
                relative_path = exported_path.name

            dest_root = Path(bpy.path.abspath(settings.copy_directory)).resolve()
            copy_path = dest_root / relative_path
            copy_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy(exported_path, copy_path)
            self.copy_count += 1
            print(f"Copied to: {copy_path}")
        except Exception as e:
            print(f"Copy failed: {e}")

    def _report_results(self, context, settings):
        """Reports the final export summary to the user."""
        prefs = context.preferences.addons[__package__].preferences
        copies_enabled = prefs.copy_on_export and settings.copy_on_export

        if self.file_count == 0:
            self.report({'WARNING'}, "Operation complete. No files were exported.")
            return

        # Build the base success message
        msg = f"Exported {self.file_count} file(s)"
        if copies_enabled and self.copy_count > 0:
            msg += f" (with {self.copy_count} copies)"

        # If we skipped any LODs, change the final report to a warning
        if hasattr(self, 'skipped_lods') and self.skipped_lods:
            msg += f". WARNING: Skipped LOD generation for {len(self.skipped_lods)} linked object(s)."
            self.report({'WARNING'}, msg)
            
            # Print the exact list to the console so the user can check which ones
            print(f"\n--- BATCH EXPORT WARNING ---")
            print(f"Skipped LOD generation for the following linked objects:")
            for name in self.skipped_lods:
                print(f"  - {name}")
            print(f"----------------------------\n")
        else:
            # Clean success
            msg += " successfully."
            self.report({'INFO'}, msg)

    # =================================================================
    # 6. INDIVIDUAL EXPORT WRAPPERS
    # Each method calls the relevant Blender operator and returns the
    # full output filepath (with extension) as a string.
    # =================================================================

    def _export_fbx(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.fbx'
        options = utils.load_operator_preset('export_scene.fbx', settings.fbx_preset)
        options.update({
            "filepath": full_path,
            "use_selection": True,
            "use_mesh_modifiers": settings.apply_mods,
        })
        bpy.ops.export_scene.fbx(**options)
        return full_path

    def _export_gltf(self, settings, fp_no_ext):
        # glTF exporter appends the extension itself when export_format is set,
        # so we pass the path without extension and let Blender handle it.
        full_path = str(fp_no_ext) + '.glb'
        options = utils.load_operator_preset('export_scene.gltf', settings.gltf_preset)
        options.update({
            "filepath": str(fp_no_ext),
            "export_format": 'GLB',
            "use_selection": True,
            "export_apply": settings.apply_mods,
        })
        bpy.ops.export_scene.gltf(**options)
        return full_path

    def _export_alembic(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.abc'
        options = utils.load_operator_preset('wm.alembic_export', settings.abc_preset)
        options.update({
            "filepath": full_path,
            "selected": True,
            "start": settings.frame_start,
            "end": settings.frame_end,
        })
        # Use EXEC_REGION_WIN to force foreground execution.
        # alembic_export runs as a background job by default (via INVOKE), which
        # breaks batch export order. The 'as_background_job' kwarg is deprecated;
        # passing an explicit execution context is the recommended workaround.
        # See: docs.blender.org/api/current/bpy.ops.html#execution-context
        bpy.ops.wm.alembic_export('EXEC_REGION_WIN', **options)
        return full_path

    def _export_usd(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + settings.usd_format
        options = utils.load_operator_preset('wm.usd_export', settings.usd_preset)
        options.update({
            "filepath": full_path,
            "selected_objects_only": True,
        })
        bpy.ops.wm.usd_export(**options)
        return full_path

    def _export_obj(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.obj'
        options = utils.load_operator_preset('wm.obj_export', settings.obj_preset)
        options.update({
            "filepath": full_path,
            "export_selected_objects": True,
            "apply_modifiers": settings.apply_mods,
        })
        bpy.ops.wm.obj_export(**options)
        return full_path

    def _export_ply(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.ply'
        bpy.ops.wm.ply_export(
            filepath=full_path,
            ascii_format=settings.ply_ascii,
            export_selected_objects=True,
            apply_modifiers=settings.apply_mods,
        )
        return full_path

    def _export_stl(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.stl'
        bpy.ops.wm.stl_export(
            filepath=full_path,
            ascii_format=settings.stl_ascii,
            export_selected_objects=True,
            apply_modifiers=settings.apply_mods,
        )
        return full_path

    def _export_svg(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.svg'
        bpy.ops.wm.gpencil_export_svg(filepath=full_path, selected_object_type='SELECTED')
        return full_path

    def _export_pdf(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.pdf'
        bpy.ops.wm.gpencil_export_pdf(filepath=full_path, selected_object_type='SELECTED')
        return full_path


registry = [
    EXPORT_MESH_OT_batch,
]
