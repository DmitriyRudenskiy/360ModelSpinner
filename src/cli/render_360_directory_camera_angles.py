import bpy
import sys
import os
import math
import hashlib
import shutil
import time
from mathutils import Vector, Matrix

# Попытка импортировать Pillow для быстрой работы с картинками вне Blender
try:
    from PIL import Image as PILImage

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARNING] Библиотека Pillow не найдена. Обложки будут создаваться средствами Blender (медленнее).")


def calculate_md5(file_path):
    """Вычисляет MD5 хеш файла по частям для экономии памяти."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def clean_scene():
    """
    Надежная очистка сцены. Удаляет все объекты и орфанные данные.
    """
    # Выход в объектный режим
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Удаление всех объектов
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Удаление орфанных данных (mesh, mat, etc.)
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)

    for block in bpy.data.textures:
        if block.users == 0:
            bpy.data.textures.remove(block)

    for block in bpy.data.images:
        if block.users == 0:
            bpy.data.images.remove(block)

    for block in bpy.data.lights:
        if block.users == 0:
            bpy.data.lights.remove(block)

    for block in bpy.data.cameras:
        if block.users == 0:
            bpy.data.cameras.remove(block)

    # Очистка памяти
    if hasattr(bpy.data, 'orphans_purge'):
        bpy.data.orphans_purge()


def create_white_material(name="White_Material"):
    """Создает стандартный белый материал для рендера."""
    mat = bpy.data.materials.new(name=name)

    # В Blender 4.0+ узлы включены по умолчанию при создании материала.
    # Строчка mat.use_nodes = True устарела и вызовет ошибку в будущем.
    # Просто получаем доступ к дереву узлов.
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.9, 0.9, 0.9, 1)
    bsdf.inputs['Roughness'].default_value = 0.5
    bsdf.inputs['Metallic'].default_value = 0.0

    # Обработка разных версий Blender (Specular vs IOR)
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.5
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.5

    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    return mat


def finalize_processing(file_path, model_name, output_dir):
    """Перемещает оригинальный файл и создает обложку."""
    print("[INFO] Финализация файла...")

    base_dir = os.path.dirname(file_path)
    ready_dir = os.path.join(base_dir, "ready")
    os.makedirs(ready_dir, exist_ok=True)

    # Путь к картинке 0 градусов
    zero_degree_img_name = f"{model_name}_000.png"
    zero_degree_img_path = os.path.join(output_dir, zero_degree_img_name)
    preview_img_name = f"{model_name}.jpg"
    preview_img_path = os.path.join(ready_dir, preview_img_name)

    # Создание превью
    if os.path.exists(zero_degree_img_path):
        print(f"[INFO] Создание JPG обложки...")

        # Способ 1: Через Pillow (быстро, требует установленной библиотеки)
        if HAS_PIL:
            try:
                with PILImage.open(zero_degree_img_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((640, 640), PILImage.Resampling.LANCZOS)
                    img.save(preview_img_path, "JPEG", quality=90)
                    print(f"[INFO] Обложка сохранена (PIL): {preview_img_path}")
            except Exception as e:
                print(f"[ERROR] Ошибка Pillow: {e}. Пробуем средствами Blender.")

        # Способ 2: Через Blender (медленно, но надежно)
        if not HAS_PIL or not os.path.exists(preview_img_path):
            try:
                img = bpy.data.images.load(zero_degree_img_path)
                img.scale(640, 640)
                img.filepath_raw = preview_img_path
                img.file_format = 'JPEG'
                img.save()
                bpy.data.images.remove(img)
                print(f"[INFO] Обложка сохранена (Blender): {preview_img_path}")
            except Exception as e:
                print(f"[ERROR] Не удалось сохранить обложку: {e}")
    else:
        print(f"[WARNING] Картинка {zero_degree_img_name} не найдена.")

    # Перемещение исходного файла
    try:
        target_file_path = os.path.join(ready_dir, os.path.basename(file_path))
        # Проверка на существование файла назначения во избежание ошибок
        if os.path.exists(target_file_path):
            os.remove(target_file_path)
        shutil.move(file_path, target_file_path)
        print(f"[INFO] Исходный файл перемещен в: {target_file_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось переместить исходный файл: {e}")
        return False


def process_file(file_path):
    """Основная обработка одного файла."""
    print(f"\n{'=' * 50}")
    print(f"[FILE] Обработка: {os.path.basename(file_path)}")
    print(f"{'=' * 50}")

    if not os.path.exists(file_path):
        print("[ERROR] Файл не найден!")
        return False

    # === Этап 1: Проверка и переименование по MD5 ===
    current_name = os.path.splitext(os.path.basename(file_path))[0]
    file_ext = os.path.splitext(file_path)[1]
    md5_hash = calculate_md5(file_path)

    if current_name != md5_hash:
        new_filename = f"{md5_hash}{file_ext}"
        new_path = os.path.join(os.path.dirname(file_path), new_filename)

        if new_path != file_path:
            try:
                if os.path.exists(new_path):
                    # Если файл с таким хешем уже есть, проверяем содержимое
                    existing_md5 = calculate_md5(new_path)
                    if existing_md5 == md5_hash:
                        print(f"[INFO] Дубликат найден. Удаляем текущий файл, обрабатываем существующий.")
                        os.remove(file_path)
                        file_path = new_path
                    else:
                        # Коллизия (маловероятно), добавляем суффикс
                        new_path = os.path.join(os.path.dirname(file_path), f"{new_filename}.new")
                        os.rename(file_path, new_path)
                        file_path = new_path
                else:
                    print(f"[INFO] Переименование файла в {new_filename}")
                    os.rename(file_path, new_path)
                    file_path = new_path
            except Exception as e:
                print(f"[ERROR] Ошибка переименования: {e}")
                return False

    # Обновляем имя модели после возможного переименования
    model_name = os.path.splitext(os.path.basename(file_path))[0]

    # === Этап 2: Подготовка сцены ===
    clean_scene()

    # === Этап 3: Импорт ===
    print(f"[INFO] Импорт файла...")
    try:
        if file_ext.lower() == '.glb':
            bpy.ops.import_scene.gltf(filepath=file_path)
        elif file_ext.lower() == '.stl':
            # Пробуем новый оператор, если нет — старый
            try:
                bpy.ops.wm.stl_import(filepath=file_path)
            except AttributeError:
                bpy.ops.import_mesh.stl(filepath=file_path)
        else:
            print(f"[ERROR] Неподдерживаемый формат: {file_ext}")
            return False
    except Exception as e:
        print(f"[ERROR] Ошибка импорта: {e}")
        return False

    # === Этап 4: Анализ и подготовка геометрии ===
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not mesh_objects:
        print("[ERROR] Объекты MESH не найдены.")
        return False

    # Быстрый расчет габаритов через bound_box (не перебираем вершины)
    min_co = Vector((float('inf'), float('inf'), float('inf')))
    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))

    for obj in mesh_objects:
        # Убедимся, что матрица мира актуальна
        obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        matrix = obj.matrix_world

        for corner in obj.bound_box:
            world_corner = matrix @ Vector(corner)
            min_co.x = min(min_co.x, world_corner.x)
            min_co.y = min(min_co.y, world_corner.y)
            min_co.z = min(min_co.z, world_corner.z)

            max_co.x = max(max_co.x, world_corner.x)
            max_co.y = max(max_co.y, world_corner.y)
            max_co.z = max(max_co.z, world_corner.z)

    center = (min_co + max_co) / 2
    size = max_co - min_co
    max_dim = max(size.x, size.y, size.z)

    print(f"[INFO] Габариты: {size.x:.2f} x {size.y:.2f} x {size.z:.2f}")

    # Центрирование через перемещение
    for obj in mesh_objects:
        obj.location -= center

    # Создаем Pivot (пустышку) для вращения
    bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.1, location=(0, 0, 0))
    pivot = bpy.context.object
    pivot.name = "Rotation_Pivot"

    # Парентим объекты к пивоту
    for obj in mesh_objects:
        obj.parent = pivot
        obj.matrix_parent_inverse = Matrix.Identity(4)

    # Нормализация масштаба
    target_size = 2.0
    if max_dim > 0:
        scale_factor = target_size / max_dim
        pivot.scale = (scale_factor, scale_factor, scale_factor)
        max_dim = target_size

    # === Этап 5: Материалы ===
    white_mat = create_white_material("Render_White")

    for obj in mesh_objects:
        # Для STL всегда ставим белый материал
        if file_ext.lower() == '.stl':
            obj.data.materials.clear()
            obj.data.materials.append(white_mat)
        # Для GLB ставим белый, только если материалов нет
        elif not obj.data.materials:
            obj.data.materials.append(white_mat)

    # === Этап 6: Камера и Свет ===
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    camera.data.lens = 50

    # Расчет расстояния
    fov = 2 * math.atan(36 / (2 * camera.data.lens))
    camera_distance = (max_dim * 0.6) / math.tan(fov / 2)
    camera_distance = max(camera_distance, 3.5)  # Минимальная дистанция

    # Создаем свет
    def add_light(name, loc, energy, size=1.0):
        bpy.ops.object.light_add(type='AREA', radius=size)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.location = loc
        # Направляем свет в центр
        direction = (Vector((0, 0, 0)) - Vector(loc)).normalized()
        rot_quat = direction.to_track_quat('-Z', 'Y')
        light.rotation_euler = rot_quat.to_euler()

    # Простая схема освещения
    add_light("Key", (-3, -camera_distance, 4), 300, size=2.0)
    add_light("Fill", (4, -camera_distance * 0.5, 2), 150, size=2.0)
    add_light("Rim", (0, camera_distance * 0.5, 5), 200, size=1.5)

    # === Этап 7: Настройки рендера ===
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'

    # === ИСПРАВЛЕНИЕ: Авто-выбор устройства ===
    # Пытаемся найти доступный тип GPU (Metal для Mac, CUDA/OptiX для других)
    # Если GPU нет, используем CPU.
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        # Получаем список доступных типов устройств
        # Обычно это ('NONE', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI', 'METAL')

        has_gpu = False
        # Приоритет поиска GPU типов
        for dev_type in ['METAL', 'OPTIX', 'CUDA', 'HIP', 'ONEAPI']:
            try:
                prefs.compute_device_type = dev_type
                # Если установка прошла успешно, проверяем, есть ли устройства
                # get_devices() возвращает список устройств
                if any(device.type in ['GPU', 'OPTIX', 'CUDA', 'METAL', 'HIP', 'ONEAPI'] for device in
                       prefs.get_devices()):
                    scene.cycles.device = 'GPU'
                    print(f"[INFO] Установлено устройство рендера: {dev_type}")
                    has_gpu = True
                    break
            except TypeError:
                # Этот тип устройства не поддерживается на текущей платформе
                continue

        if not has_gpu:
            scene.cycles.device = 'CPU'
            print("[INFO] GPU не найден или не поддерживается, используется CPU.")

    except Exception as e:
        print(f"[WARNING] Ошибка при настройке устройства рендеринга: {e}. Используем CPU.")
        scene.cycles.device = 'CPU'

    scene.cycles.samples = 64
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'

    # === Этап 8: Рендеринг ===
    output_dir = os.path.join(os.path.dirname(file_path), "renders")
    os.makedirs(output_dir, exist_ok=True)

    # Устанавливаем камеру активной
    scene.camera = camera

    camera_angles = [-30, -15, 0, 15, 30]
    steps = 36
    total_rendered = 0

    for cam_angle in camera_angles:
        # Позиционирование камеры
        phi = math.radians(cam_angle)
        cam_y = -camera_distance * math.cos(phi)
        cam_z = camera_distance * math.sin(phi)
        camera.location = (0, cam_y, cam_z)

        # Смотрим в центр
        direction = (Vector((0, 0, 0)) - camera.location).normalized()
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        for i in range(steps):
            rot_angle = round((360 / steps) * i)

            # Формирование имени файла
            if cam_angle == 0:
                file_name = f"{model_name}_{rot_angle:03d}.png"
            else:
                suffix = f"_e{cam_angle:+d}"
                file_name = f"{model_name}_{rot_angle:03d}{suffix}.png"

            file_path_render = os.path.join(output_dir, file_name)

            if os.path.exists(file_path_render):
                continue  # Пропускаем существующие

            pivot.rotation_euler = (0, 0, math.radians(rot_angle))

            # Обновление сцены перед рендером
            bpy.context.view_layer.update()

            scene.render.filepath = file_path_render
            try:
                bpy.ops.render.render(write_still=True)
                total_rendered += 1
            except Exception as e:
                print(f"[ERROR] Ошибка рендера: {e}")

    print(f"[INFO] Рендеринг завершен. Изображений сохранено: {total_rendered}")

    # === Этап 9: Финализация ===
    if not finalize_processing(file_path, model_name, output_dir):
        return False

    return True


def process_directory(directory_path):
    """Обработка всех файлов в директории."""
    supported_files = []
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(('.glb', '.stl')):
            supported_files.append(os.path.join(directory_path, filename))

    if not supported_files:
        print("[WARNING] Файлы не найдены.")
        return

    print(f"[INFO] Найдено файлов: {len(supported_files)}")

    for file_path in supported_files:
        try:
            process_file(file_path)
        except Exception as e:
            print(f"[CRITICAL] Ошибка обработки файла {file_path}: {e}")
            import traceback
            traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("[ERROR] Укажите путь к файлу или папке.")
        return

    input_path = sys.argv[-1]

    if os.path.isdir(input_path):
        process_directory(input_path)
    elif os.path.isfile(input_path):
        process_file(input_path)
    else:
        print("[ERROR] Путь не найден.")


if __name__ == "__main__":
    main()