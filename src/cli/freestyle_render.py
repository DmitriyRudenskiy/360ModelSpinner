import bpy
import sys
import os
import argparse
import math
import addon_utils
from mathutils import Vector, Color


def parse_args():
    """Парсинг аргументов командной строки, передаваемых после разделителя '--'."""
    parser = argparse.ArgumentParser(description="Freestyle Line Art для 3D-моделей в Blender")
    parser.add_argument("-i", "--input", required=True, help="Путь к входному файлу (.stl, .glb, .gltf)")
    parser.add_argument("-o", "--output", required=True, help="Путь для сохранения результата (.png)")
    parser.add_argument("-r", "--resolution", type=int, required=True, help="Разрешение по большей стороне в пикселях")
    parser.add_argument("--thickness", type=float, default=1.0, help="Толщина линий в пикселях (по умолчанию 1.0)")
    parser.add_argument("--color", type=float, nargs=4, default=[0, 0, 0, 1],
                        help="Цвет линий RGBA (0-1), по умолчанию черный")

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
        line_thickness = args.thickness
        line_color = tuple(args.color)

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

        # --- 3. Импорт модели ---
        if ext == '.stl':
            try:
                bpy.ops.wm.stl_import(filepath=input_path)
            except AttributeError:
                bpy.ops.import_mesh.stl(filepath=input_path)
        elif ext in ['.glb', '.gltf']:
            try:
                addon_utils.enable('io_scene_gltf2')
            except Exception:
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

        # Назначение простого материала
        mat = bpy.data.materials.new(name="SimpleMat")
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            for n in nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    bsdf = n
                    break

        if bsdf:
            try:
                bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
                bsdf.inputs['Roughness'].default_value = 0.5
            except KeyError:
                if len(bsdf.inputs) > 0:
                    bsdf.inputs[0].default_value = (0.8, 0.8, 0.8, 1.0)
                if len(bsdf.inputs) > 2:
                    bsdf.inputs[2].default_value = 0.5

        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        # --- 5. Настройка сцены (Камера и Свет) ---
        scene = bpy.context.scene

        engines = [item.identifier for item in scene.render.bl_rna.properties['engine'].enum_items]
        if 'BLENDER_EEVEE_NEXT' in engines:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        elif 'BLENDER_EEVEE' in engines:
            scene.render.engine = 'BLENDER_EEVEE'
        else:
            scene.render.engine = 'BLENDER_WORKBENCH'

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

        light_data = bpy.data.lights.new(name="Sun", type='SUN')
        light_data.energy = 3.0
        light_data.color = (1, 1, 1)
        light_obj = bpy.data.objects.new("Sun", light_data)
        scene.collection.objects.link(light_obj)
        light_obj.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))

        # --- 6. Настройка Freestyle (Исправлено для Blender 5.0) ---
        scene.render.use_freestyle = True

        # Получаем текущий View Layer
        view_layer = bpy.context.view_layer
        view_layer.use_freestyle = True

        # Создаем LineSet для контуров
        lineset = view_layer.freestyle_settings.linesets.new("Edges")

        # Включаем нужные типы линий (Blender 5.0 API: select_* вместо show_*)
        lineset.select_silhouette = True  # Силуэты (внешние контуры)
        lineset.select_border = True  # Границы между объектами
        lineset.select_crease = True  # Острые грани (creases)
        lineset.select_edge_mark = True  # Помеченные ребра
        lineset.select_suggestive_contour = False  # Отключаем (создают шум)
        lineset.select_ridge_valley = False  # Отключаем (избегаем лишних линий)

        # Настраиваем стиль линии
        linestyle = lineset.linestyle
        linestyle.color = Color(line_color[:3])  # RGB (mathutils.Color)
        linestyle.alpha = line_color[3] if len(line_color) > 3 else 1.0
        linestyle.thickness = line_thickness

        # Используем простое связывание (plain chaining)
        linestyle.use_chaining = True
        linestyle.chaining = 'PLAIN'
        linestyle.use_same_object = False

        # Опционально: белый фон
        scene.world.use_nodes = True
        bg_node = scene.world.node_tree.nodes.get("Background")
        if bg_node:
            bg_node.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)

        # --- 7. Рендер и сохранение ---
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = output_path
        scene.render.use_file_extension = False

        bpy.ops.render.render(write_still=True)
        print(f"Успех: Результат сохранен в {output_path}")

    except Exception as e:
        print(f"Критическая ошибка при выполнении скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()