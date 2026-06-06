import bpy
import sys
import os
import argparse
import math
from mathutils import Vector


def parse_args():
    """Парсинг аргументов командной строки, передаваемых после разделителя '--'."""
    parser = argparse.ArgumentParser(description="Freestyle Line Art рендер для 3D-моделей в Blender")
    parser.add_argument("-i", "--input", required=True, help="Путь к входному файлу (.stl, .glb, .gltf)")
    parser.add_argument("-o", "--output", required=True, help="Путь для сохранения результата (.png)")
    parser.add_argument("-r", "--resolution", type=int, required=True, help="Разрешение по большей стороне в пикселях")

    if '--' in sys.argv:
        argv = sys.argv[sys.argv.index('--') + 1:]
    else:
        argv = sys.argv[1:]

    return parser.parse_args(argv)


def main():
    try:
        args = parse_args()

        input_path = args.input
        output_path = os.path.abspath(args.output)
        resolution = args.resolution

        # --- 1. Валидация входных данных ---
        if not os.path.exists(input_path):
            print(f"Ошибка: Входной файл не найден: {input_path}")
            sys.exit(1)

        ext = os.path.splitext(input_path)[1].lower()
        if ext not in ['.stl', '.glb', '.gltf']:
            print(f"Ошибка: Неподдерживаемый формат: {ext}. Разрешены только .stl, .glb, .gltf")
            sys.exit(1)

        if not output_path.lower().endswith('.png'):
            print(f"Ошибка: Выходной файл должен иметь расширение .png")
            sys.exit(1)

        # --- 2. Очистка сцены ---
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

        # Очищаем данные
        for block in bpy.data.meshes:
            if block.users == 0:
                bpy.data.meshes.remove(block)
        for block in bpy.data.materials:
            if block.users == 0:
                bpy.data.materials.remove(block)

        # --- 3. Импорт модели ---
        if ext == '.stl':
            try:
                bpy.ops.wm.stl_import(filepath=input_path)
            except AttributeError:
                bpy.ops.import_mesh.stl(filepath=input_path)
        elif ext in ['.glb', '.gltf']:
            try:
                bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
            except Exception:
                pass
            bpy.ops.import_scene.gltf(filepath=input_path)

        # --- 4. Подготовка модели ---
        imported_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not imported_objects:
            print("Ошибка: В файле не найдено мешей.")
            sys.exit(1)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in imported_objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = imported_objects[0]

        if len(imported_objects) > 1:
            bpy.ops.object.join()

        obj = bpy.context.active_object

        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_bound = Vector(
            (min(c.x for c in bbox_corners), min(c.y for c in bbox_corners), min(c.z for c in bbox_corners)))
        max_bound = Vector(
            (max(c.x for c in bbox_corners), max(c.y for c in bbox_corners), max(c.z for c in bbox_corners)))
        center = (min_bound + max_bound) / 2.0

        obj.location -= center
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_bound = Vector(
            (min(c.x for c in bbox_corners), min(c.y for c in bbox_corners), min(c.z for c in bbox_corners)))
        max_bound = Vector(
            (max(c.x for c in bbox_corners), max(c.y for c in bbox_corners), max(c.z for c in bbox_corners)))
        size = max_bound - min_bound

        # --- Настройка сглаживания (Исправлено для Blender 5.0) ---
        bpy.ops.object.shade_smooth()
        bpy.ops.object.shade_auto_smooth()

        mod = obj.modifiers.get("Smooth by Angle")
        if mod and mod.type == 'NODES':
            try:
                angle_input = mod.inputs.get("Angle")
                if angle_input:
                    angle_input.default_value = math.radians(35)
            except Exception:
                pass

        # --- Материал: Черный (для слияния с фоном) ---
        mat = bpy.data.materials.new(name="BlackMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            # Устанавливаем черный цвет модели
            bsdf.inputs['Base Color'].default_value = (0.0, 0.0, 0.0, 1.0)

        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        # --- 5. Настройка сцены (Камера и Мир) ---
        scene = bpy.context.scene

        engines = [item.identifier for item in scene.render.bl_rna.properties['engine'].enum_items]
        if 'BLENDER_EEVEE_NEXT' in engines:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        elif 'BLENDER_EEVEE' in engines:
            scene.render.engine = 'BLENDER_EEVEE'
        else:
            scene.render.engine = 'BLENDER_WORKBENCH'

        # --- Мир (Фон): Черный ---
        world = bpy.data.worlds.get("World")
        if not world:
            world = bpy.data.worlds.new("World")
        scene.world = world

        if world.use_nodes:
            bg_node = world.node_tree.nodes.get("Background")
            if bg_node:
                # Устанавливаем черный цвет фона
                bg_node.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
                bg_node.inputs['Strength'].default_value = 1.0
        else:
            world.color = (0.0, 0.0, 0.0)

        # Камера
        cam_data = bpy.data.cameras.new(name="Camera")
        cam_obj = bpy.data.objects.new("Camera", cam_data)
        scene.collection.objects.link(cam_obj)
        scene.camera = cam_obj

        cam_data.type = 'ORTHO'
        size_x = max_bound.x - min_bound.x
        size_z = max_bound.z - min_bound.z

        if size_x > size_z:
            res_x = resolution
            res_y = max(1, int(resolution * (size_z / size_x))) if size_x > 0 else resolution
        else:
            res_y = resolution
            res_x = max(1, int(resolution * (size_x / size_z))) if size_z > 0 else resolution

        scene.render.resolution_x = res_x
        scene.render.resolution_y = res_y
        scene.render.resolution_percentage = 100

        cam_data.ortho_scale = max(size.x, size.z, 0.1) * 1.2

        dist = max(size.x, size.y, size.z) * 2.0
        cam_loc = Vector((0, -dist, 0))
        cam_obj.location = cam_loc
        direction = Vector((0, 0, 0)) - cam_loc
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = rot_quat.to_euler()

        # --- 6. Настройка Freestyle (Белые линии) ---
        scene.render.use_freestyle = True
        view_layer = scene.view_layers["ViewLayer"]
        view_layer.use_freestyle = True

        linesets = view_layer.freestyle_settings.linesets
        while linesets:
            linesets.remove(linesets[0])

        lineset = linesets.new(name="LineArtSet")

        lineset.select_silhouette = True
        lineset.select_crease = True
        lineset.select_border = True

        linestyle = lineset.linestyle
        linestyle.thickness = 1.0

        # Устанавливаем белый цвет линий
        linestyle.color = (1.0, 1.0, 1.0)

        # --- 7. Рендер и сохранение ---
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = output_path
        scene.render.use_file_extension = False

        bpy.ops.render.render(write_still=True)
        print(f"Успех: Результат (White Lines on Black) сохранен в {output_path}")

    except Exception as e:
        print(f"Критическая ошибка при выполнении скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()