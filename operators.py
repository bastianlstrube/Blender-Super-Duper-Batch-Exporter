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
        self.file_count = 0
        self.copy_count = 0
        self.skipped_lods = []
        self.failed_jobs = []
        settings = context.scene.batch_export
        prefs = context.preferences.addons[__package__].preferences

        try:
            base_dir = utils.resolve_base_dir(settings, prefs)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        if not base_dir.is_dir():
            self.report({'ERROR'}, f"Export directory does not exist:\n{base_dir}")
            return {'CANCELLED'}

        filtered_objects = self._get_filtered_objects(context, settings)
        if not filtered_objects:
            self.report({'WARNING'}, "No objects matched the filter settings.")
            return {'FINISHED'}

        with self._preserve_blender_state(context):
            jobs = list(self._generate_export_jobs(settings, filtered_objects, base_dir))

            collisions = self._detect_collisions(settings, jobs)
            if collisions:
                self.report(
                    {'WARNING'},
                    f"{len(collisions)} file(s) share an output path and will "
                    f"overwrite each other: {', '.join(collisions)}"
                )

            wm = context.window_manager
            wm.progress_begin(0, len(jobs))
            try:
                for i, job in enumerate(jobs):
                    try:
                        self._process_export_job(context, settings, job)
                    except Exception as e:
                        self.failed_jobs.append(job['name'])
                        print(f"Failed to export '{job['name']}': {e}")
                        import traceback
                        traceback.print_exc()
                    wm.progress_update(i + 1)
            finally:
                wm.progress_end()

        self._report_results(context, settings)
        return {'FINISHED'}

    # =================================================================
    # 1. VALIDATION AND SETUP
    # =================================================================

    def _detect_collisions(self, settings, jobs):
        seen = set()
        collisions = []
        for job in jobs:
            prefix = job.get('prefix', settings.prefix)
            suffix = job.get('suffix', settings.suffix)
            clean_name = prefix + bpy.path.clean_name(job['name']) + suffix
            key = str((job['directory'] / clean_name).resolve())
            if key in seen:
                collisions.append(clean_name)
            else:
                seen.add(key)
        return collisions

    def _resolve_tokens(self, text, source_obj=None, collection=None):
        """Replaces interpolation tokens and normalizes paths to universal forward slashes."""
        if not text:
            return ""
            
        import datetime
        
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
            obj_name = bpy.path.clean_name(source_obj.name)
            text = text.replace("$OBJ", obj_name)
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
            hierarchy = utils.get_collection_hierarchy(coll_to_use.name)
            if hierarchy:
                coll_path = hierarchy.replace("\\", "/")
            else:
                coll_path = coll_name
                
        text = text.replace("$COLL_PATH", coll_path)
        text = text.replace("$COLL", coll_name)
        
        # 5. Temporal stamps
        now = datetime.datetime.now()
        text = text.replace("$DATE", now.strftime("%Y-%m-%d"))
        text = text.replace("$TIME", now.strftime("%H%M%S"))
        
        return text

    # =================================================================
    # 2. STATE MANAGEMENT (CONTEXT MANAGERS)
    # =================================================================

    @contextmanager
    def _preserve_blender_state(self, context):
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
                    is_editable = (not original_active.library and not (original_active.override_library and original_active.override_library.is_system_override))
                    if is_editable:
                        try:
                            bpy.ops.object.mode_set(mode=original_mode)
                        except RuntimeError:
                            pass

    @contextmanager
    def _temporary_visibility(self, objects):
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
        original_transforms = {
            obj: (obj.location.copy(), obj.rotation_euler.copy(), obj.scale.copy())
            for obj in objects_to_transform
        }
        try:
            for obj in objects_to_transform:
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
    def _temporary_apply_transform(self, settings, objects_to_apply):
        if not (settings.apply_location or settings.apply_rotation or settings.apply_scale):
            yield
            return

        data_backups = {}
        transform_backups = {}

        for obj in objects_to_apply:
            if obj is None or obj.data is None or not hasattr(obj.data, 'copy'):
                continue
            if obj.library or (obj.override_library and obj.override_library.is_system_override):
                continue
            data_backups[obj] = obj.data
            transform_backups[obj] = (
                obj.location.copy(),
                obj.rotation_euler.copy(),
                obj.rotation_quaternion.copy(),
                obj.scale.copy(),
            )
            obj.data = obj.data.copy()

        try:
            if data_backups:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in data_backups:
                    try:
                        obj.select_set(True)
                    except RuntimeError:
                        pass
                first = next(iter(data_backups))
                bpy.context.view_layer.objects.active = first

                try:
                    bpy.ops.object.transform_apply(
                        location=settings.apply_location,
                        rotation=settings.apply_rotation,
                        scale=settings.apply_scale,
                        properties=False,
                        corrective_flip_normals=settings.corrective_flip_normals,
                    )
                except RuntimeError as e:
                    print(f"transform_apply failed: {e}")
                bpy.context.view_layer.update()
            yield
        finally:
            for obj, original in data_backups.items():
                if obj is None or obj.name not in bpy.data.objects:
                    continue
                temp = obj.data
                obj.data = original
                loc, rot_e, rot_q, scl = transform_backups[obj]
                obj.location = loc
                obj.rotation_euler = rot_e
                obj.rotation_quaternion = rot_q
                obj.scale = scl
                if temp is None or temp == original:
                    continue
                try:
                    if isinstance(temp, bpy.types.Mesh): bpy.data.meshes.remove(temp)
                    elif isinstance(temp, bpy.types.Curve): bpy.data.curves.remove(temp)
                    elif isinstance(temp, bpy.types.MetaBall): bpy.data.metaballs.remove(temp)
                    elif isinstance(temp, bpy.types.Lattice): bpy.data.lattices.remove(temp)
                    elif isinstance(temp, bpy.types.Armature): bpy.data.armatures.remove(temp)
                except Exception as e:
                    print(f"Could not free temporary data for {obj.name}: {e}")

    @contextmanager
    def _managed_lods(self, settings, obj):
        is_editable = (not obj.library and not (obj.override_library and obj.override_library.is_system_override))
        wants_lods = settings.create_lod and settings.file_format in {'FBX', 'glTF'} and obj.type == 'MESH'

        if wants_lods and not is_editable:
            self.skipped_lods.append(obj.name)
            self.report({'WARNING'}, f"Skipped LODs for '{obj.name}' (Linked Object, cannot edit). Exporting base mesh only.")
            yield [obj]
            return

        if not wants_lods:
            yield [obj]
            return

        lod_objects = []
        original_name = obj.name
        original_parent = obj.parent
        original_apply_mods = settings.apply_mods
        collection = obj.users_collection[0]

        try:
            obj.name = f"{original_name}_preLOD"
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

            lod0 = obj.copy()
            lod0.data = lod0.data.copy()
            lod0.name = f"{original_name}_LOD0"
            collection.objects.link(lod0)
            lod0.parent = lod_parent
            lod0.matrix_local.identity()
            lod_objects.append(lod0)

            for i in range(settings.lod_count):
                lod_ratio = getattr(settings, f"lod{i + 1}_ratio")
                if lod_ratio >= 1.0: continue
                lod = lod0.copy()
                lod.data = lod0.data.copy()
                lod.name = f"{original_name}_LOD{i + 1}"
                collection.objects.link(lod)
                lod.parent = lod_parent
                lod.matrix_local.identity()
                mod = lod.modifiers.new(name='DecimateLOD', type='DECIMATE')
                mod.ratio = lod_ratio
                lod_objects.append(lod)

            settings.apply_mods = True
            yield lod_objects
        finally:
            settings.apply_mods = original_apply_mods
            for lod_obj in lod_objects:
                if lod_obj and lod_obj.name in bpy.data.objects:
                    bpy.data.objects.remove(lod_obj, do_unlink=True)
            if obj and obj.name.endswith('_preLOD'):
                obj.name = original_name

    # =================================================================
    # 3. OBJECT GATHERING AND JOB CREATION
    # =================================================================

    def _get_filtered_objects(self, context, settings):
        limit = settings.limit
        if limit == 'SELECTED': source = context.selected_objects[:]
        elif limit == 'VISIBLE': source = [obj for obj in context.view_layer.objects if obj.visible_get()]
        elif limit == 'RENDERABLE':
            renderable_names = {obj.name for obj in self._get_renderable_objects(context.scene)}
            source = [obj for obj in context.view_layer.objects if obj.name in renderable_names]
        elif limit == 'LIST':
            list_objects = {item.object for item in settings.export_list if item.object is not None}
            source = [obj for obj in context.view_layer.objects if obj in list_objects]
        else: source = []

        return [obj for obj in source if obj.type in settings.object_types]

    def _get_renderable_objects(self, scene):
        renderable = []
        def check_collection(collection):
            if collection.hide_render: return
            for obj in collection.objects:
                if not obj.hide_render: renderable.append(obj)
            for child in collection.children: check_collection(child)
        check_collection(scene.collection)
        return renderable

    def _generate_export_jobs(self, settings, objects, base_dir):
        mode = settings.mode
        object_set = set(objects)

        if mode == 'OBJECTS':
            for obj in objects:
                yield self._build_job(settings, obj.name, [obj], base_dir, source_obj=obj)
        elif mode == 'PARENT_OBJECTS':
            for obj in objects:
                if obj.parent in object_set: continue
                children = [c for c in obj.children_recursive if c in object_set]
                yield self._build_job(settings, obj.name, [obj] + children, base_dir, source_obj=obj)
        elif mode == 'COLLECTIONS':
            collections_map = {}
            for obj in objects:
                if obj.users_collection:
                    primary = obj.users_collection[0]
                    collections_map.setdefault(primary, []).append(obj)
            for coll, coll_objects in collections_map.items():
                yield self._build_job(settings, coll.name, coll_objects, base_dir, collection=coll)
        elif mode == 'SCENE':
            filename = Path(bpy.data.filepath).with_suffix('').name if bpy.data.is_saved else "Untitled"
            yield self._build_job(settings, filename, objects, base_dir)

    def _build_job(self, settings, name, objects, base_dir, source_obj=None, collection=None):
        item_name = name

        resolved_prefix = self._resolve_tokens(settings.prefix, source_obj, collection)
        resolved_suffix = self._resolve_tokens(settings.suffix, source_obj, collection)

        if settings.prefix_collection and 'OBJECT' in settings.mode and source_obj and source_obj.users_collection:
            collection_name = source_obj.users_collection[0].name
            if collection_name != 'Scene Collection':
                item_name = f"{collection_name}_{item_name}"

        return {
            'name': item_name, 
            'objects': objects, 
            'directory': base_dir,
            'prefix': resolved_prefix,
            'suffix': resolved_suffix
        }

    # =================================================================
    # 4. CORE EXPORT PROCESSING
    # =================================================================

    def _process_export_job(self, context, settings, job):
        if not job['objects']: return
        bpy.ops.object.select_all(action='DESELECT')
        try:
            with self._temporary_visibility(job['objects']):
                with self._temporary_apply_transform(settings, job['objects']):
                    with self._temporary_transform(settings, job['objects']):
                        is_lod_job = (settings.create_lod and settings.file_format in {'FBX', 'glTF'} and len(job['objects']) == 1 and job['objects'][0].type == 'MESH')
                        if is_lod_job:
                            with self._managed_lods(settings, job['objects'][0]) as lod_objects:
                                self._select_and_export(settings, job, lod_objects)
                        else:
                            self._select_and_export(settings, job, job['objects'])
        finally:
            bpy.ops.object.select_all(action='DESELECT')

    def _select_and_export(self, settings, job, objects_to_export):
        for obj in objects_to_export:
            if obj and obj.name in bpy.data.objects: obj.select_set(True)
        filepath = self._dispatch_export(settings, job)
        if filepath:
            self.file_count += 1
            self._copy_exported_file(settings, filepath)

    def _dispatch_export(self, settings, job):
        prefix = job.get('prefix', settings.prefix)
        suffix = job.get('suffix', settings.suffix)
        clean_name = prefix + bpy.path.clean_name(job['name']) + suffix

        fp_no_ext = job['directory'] / clean_name
        fp_no_ext.parent.mkdir(parents=True, exist_ok=True)

        fmt = settings.file_format
        if fmt == 'FBX': return self._export_fbx(settings, fp_no_ext)
        elif fmt == 'glTF': return self._export_gltf(settings, fp_no_ext)
        elif fmt == 'ABC': return self._export_alembic(settings, fp_no_ext)
        elif fmt == 'USD': return self._export_usd(settings, fp_no_ext)
        elif fmt == 'OBJ': return self._export_obj(settings, fp_no_ext)
        elif fmt == 'PLY': return self._export_ply(settings, fp_no_ext)
        elif fmt == 'STL': return self._export_stl(settings, fp_no_ext)
        elif fmt == 'SVG': return self._export_svg(settings, fp_no_ext)
        elif fmt == 'PDF': return self._export_pdf(settings, fp_no_ext)
        return None

    # =================================================================
    # 5. POST-PROCESSING AND REPORTING
    # =================================================================

    def _copy_exported_file(self, settings, exported_file_path):
        prefs = bpy.context.preferences.addons[__package__].preferences
        if not (prefs.copy_on_export and settings.copy_on_export): return
        exported_path = Path(exported_file_path)
        if not exported_path.exists(): return
        try:
            main_export_root = utils.resolve_base_dir(settings, prefs)
            try: relative_path = exported_path.relative_to(main_export_root)
            except ValueError: relative_path = exported_path.name
            dest_root = Path(bpy.path.abspath(settings.copy_directory)).resolve()
            copy_path = dest_root / relative_path
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(exported_path, copy_path)
            self.copy_count += 1
        except Exception as e: print(f"Copy failed: {e}")

    def _report_results(self, context, settings):
        prefs = context.preferences.addons[__package__].preferences
        copies_enabled = prefs.copy_on_export and settings.copy_on_export
        failed = self.failed_jobs

        if self.file_count == 0:
            if failed: self.report({'ERROR'}, f"Export failed for all {len(failed)} job(s).")
            else: self.report({'WARNING'}, "Operation complete. No files were exported.")
            return

        msg = f"Exported {self.file_count} file(s)"
        if copies_enabled and self.copy_count > 0: msg += f" (with {self.copy_count} copies)"
        level = 'INFO'
        if failed:
            msg += f". FAILED: {len(failed)} job(s) - {', '.join(failed)}"
            level = 'WARNING'
        if self.skipped_lods:
            msg += f". Skipped LOD generation for {len(self.skipped_lods)} linked object(s)."
            level = 'WARNING'
        if level == 'INFO': msg += " successfully."
        self.report({level}, msg)

    # =================================================================
    # 6. INDIVIDUAL EXPORT WRAPPERS
    # =================================================================

    def _export_fbx(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.fbx'
        options = utils.load_operator_preset('export_scene.fbx', settings.fbx_preset)
        options.update({"filepath": full_path, "use_selection": True, "use_mesh_modifiers": settings.apply_mods})
        bpy.ops.export_scene.fbx(**options)
        return full_path

    def _export_gltf(self, settings, fp_no_ext):
        ext = '.glb' if settings.gltf_format == 'GLB' else '.gltf'
        full_path = str(fp_no_ext) + ext
        options = utils.load_operator_preset('export_scene.gltf', settings.gltf_preset)
        options.update({"filepath": str(fp_no_ext), "export_format": settings.gltf_format, "use_selection": True, "export_apply": settings.apply_mods})
        bpy.ops.export_scene.gltf(**options)
        return full_path

    def _export_alembic(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.abc'
        options = utils.load_operator_preset('wm.alembic_export', settings.abc_preset)
        options.update({"filepath": full_path, "selected": True, "start": settings.frame_start, "end": settings.frame_end})
        bpy.ops.wm.alembic_export('EXEC_REGION_WIN', **options)
        return full_path

    def _export_usd(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + settings.usd_format
        options = utils.load_operator_preset('wm.usd_export', settings.usd_preset)
        options.update({"filepath": full_path, "selected_objects_only": True, "export_animation": settings.usd_export_animation})
        bpy.ops.wm.usd_export(**options)
        return full_path

    def _export_obj(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.obj'
        options = utils.load_operator_preset('wm.obj_export', settings.obj_preset)
        options.update({"filepath": full_path, "export_selected_objects": True, "apply_modifiers": settings.apply_mods})
        bpy.ops.wm.obj_export(**options)
        return full_path

    def _export_ply(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.ply'
        bpy.ops.wm.ply_export(filepath=full_path, ascii_format=settings.ply_ascii, export_selected_objects=True, apply_modifiers=settings.apply_mods)
        return full_path

    def _export_stl(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.stl'
        bpy.ops.wm.stl_export(filepath=full_path, ascii_format=settings.stl_ascii, export_selected_objects=True, apply_modifiers=settings.apply_mods)
        return full_path

    def _export_svg(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.svg'
        bpy.ops.wm.gpencil_export_svg(filepath=full_path, selected_object_type='SELECTED')
        return full_path

    def _export_pdf(self, settings, fp_no_ext):
        full_path = str(fp_no_ext) + '.pdf'
        bpy.ops.wm.gpencil_export_pdf(filepath=full_path, selected_object_type='SELECTED')
        return full_path


class BATCH_EXPORT_OT_list_add(Operator):
    """Add selected objects to the export list"""
    bl_idname = "batch_export.list_add"
    bl_label = "Add Selected to Export List"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.batch_export
        selected = context.selected_objects
        if not selected:
            self.report({'WARNING'}, "No objects selected.")
            return {'CANCELLED'}

        existing = {item.object for item in settings.export_list if item.object is not None}
        added = 0
        for obj in selected:
            if obj not in existing:
                item = settings.export_list.add()
                item.object = obj
                added += 1
        if added:
            settings.export_list_index = len(settings.export_list) - 1
            self.report({'INFO'}, f"Added {added} object(s) to export list.")
        else:
            self.report({'INFO'}, "Selected objects are already in the list.")
        return {'FINISHED'}


class BATCH_EXPORT_OT_list_remove(Operator):
    """Remove the active object from the export list"""
    bl_idname = "batch_export.list_remove"
    bl_label = "Remove from Export List"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.batch_export.export_list) > 0

    def execute(self, context):
        settings = context.scene.batch_export
        idx = settings.export_list_index
        if 0 <= idx < len(settings.export_list):
            settings.export_list.remove(idx)
            settings.export_list_index = max(0, idx - 1)
        return {'FINISHED'}


class BATCH_EXPORT_OT_list_remove_invalid(Operator):
    """Remove deleted or invalid objects from the export list"""
    bl_idname = "batch_export.list_remove_invalid"
    bl_label = "Remove Invalid Entries"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.batch_export.export_list) > 0

    def execute(self, context):
        settings = context.scene.batch_export
        removed = 0
        for i in range(len(settings.export_list) - 1, -1, -1):
            if settings.export_list[i].object is None:
                settings.export_list.remove(i)
                removed += 1
        if removed:
            last = max(0, len(settings.export_list) - 1)
            settings.export_list_index = min(settings.export_list_index, last)
            self.report({'INFO'}, f"Removed {removed} invalid entry(ies).")
        else:
            self.report({'INFO'}, "No invalid entries found.")
        return {'FINISHED'}


class BATCH_EXPORT_OT_open_directory(Operator):
    """Open the export directory in the system file browser"""
    bl_idname = "batch_export.open_directory"
    bl_label = "Open Export Folder"

    def execute(self, context):
        settings = context.scene.batch_export
        prefs = context.preferences.addons[__package__].preferences
        try: base_dir = utils.resolve_base_dir(settings, prefs)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        if not base_dir.is_dir():
            self.report({'ERROR'}, f"Export directory does not exist:\n{base_dir}")
            return {'CANCELLED'}

        bpy.ops.wm.path_open(filepath=str(base_dir))
        return {'FINISHED'}


registry = [
    EXPORT_MESH_OT_batch,
    BATCH_EXPORT_OT_list_add,
    BATCH_EXPORT_OT_list_remove,
    BATCH_EXPORT_OT_list_remove_invalid,
    BATCH_EXPORT_OT_open_directory,
]