import bpy
import sys
import os
import math
import hashlib
from mathutils import Vector, Matrix


def calculate_md5(file_path):
    """Вычисляет MD5 хеш файла по частям для экономии памяти"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def process_file(file_path):
    """Основная обработка одного файла"""
    print(f"\n{'=' * 40}")
    print(f"[FILE] Начало обработки: {os.path.basename(file_path)}")
    print(f"{'=' * 40}")

    # Проверка существования файла
    if not os.path.exists(file_path):
        print("[ERROR] Файл не найден!")
        return False

    # === Проверка имени файла по MD5 хешу ===
    current_name = os.path.splitext(os.path.basename(file_path))[0]
    md5_hash = calculate_md5(file_path)

    if current_name != md5_hash:
        new_filename = f"{md5_hash}{os.path.splitext(file_path)[1]}"
        new_path = os.path.join(os.path.dirname(file_path), new_filename)

        # Проверяем, не совпадает ли новый путь со старым
        if new_path != file_path:
            try:
                # Если файл с именем MD5 уже существует - проверяем его содержимое
                if os.path.exists(new_path):
                    existing_md5 = calculate_md5(new_path)
                    if existing_md5 == md5_hash:
                        print(f"[INFO] Файл с именем MD5 уже существует: {new_filename}")
                        print(f"[INFO] Удаляем исходный файл: {os.path.basename(file_path)}")
                        os.remove(file_path)
                        file_path = new_path  # Продолжаем работу с существующим файлом
                    else:
                        print(f"[WARNING] Коллизия имен: файл {new_filename} существует, но имеет разное содержимое!")
                        print(f"[INFO] Переименовываем текущий файл в {new_filename}.new")
                        new_path = os.path.join(os.path.dirname(file_path), f"{new_filename}.new")
                        os.rename(file_path, new_path)
                        file_path = new_path
                else:
                    print(f"[INFO] Переименовываем файл в {new_filename}")
                    os.rename(file_path, new_path)
                    file_path = new_path  # Обновляем путь для дальнейшей обработки
            except Exception as e:
                print(f"[ERROR] Не удалось обработать имя файла: {e}")
                return False

        # Перезапускаем обработку с новым путем
        print("[INFO] Перезапуск обработки с новым именем файла...")
        return process_file(file_path)
    # === Проверка завершена ===

    # Очистка сцены
    print("[INFO] Очистка сцены...")
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Импорт файла
    print(f"[INFO] Импорт файла: {os.path.basename(file_path)}")
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.glb':
            bpy.ops.import_scene.gltf(filepath=file_path)
        elif ext == '.stl':
            bpy.ops.import_mesh.stl(filepath=file_path)
        else:
            print(f"[ERROR] Неподдерживаемый формат файла: {ext}")
            return False
    except Exception as e:
        print(f"[ERROR] Ошибка импорта {ext.upper()}: {e}")
        return False

    # Центрирование модели
    print("[INFO] Центрирование модели...")
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

    if not mesh_objects:
        print("[ERROR] Не найдено объектов типа MESH после импорта.")
        return False

    all_coords = []
    for obj in mesh_objects:
        matrix = obj.matrix_world
        for v in obj.data.vertices:
            all_coords.append(matrix @ v.co)

    if all_coords:
        min_co = Vector(map(min, zip(*all_coords)))
        max_co = Vector(map(max, zip(*all_coords)))
        center = (min_co + max_co) / 2
        size = max_co - min_co
        max_dim = max(size.x, size.y, size.z)
    else:
        center = Vector((0, 0, 0))
        max_dim = 1.0

    # Создание пустышки для вращения
    print("[INFO] Создание точки вращения...")
    bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.1, location=center)
    pivot = bpy.context.object
    pivot.name = "Rotation_Pivot"

    # Связываем все объекты модели с пустышкой
    for obj in mesh_objects:
        obj.parent = pivot
        obj.matrix_parent_inverse = Matrix.Identity(4)

    # Масштабирование модели
    if max_dim > 0:
        scale_factor = max(1.2 / max_dim, 0.9)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in mesh_objects:
            obj.select_set(True)
        bpy.ops.transform.resize(value=(scale_factor, scale_factor, scale_factor))
        bpy.ops.object.select_all(action='DESELECT')

    # Настройка камеры
    print("[INFO] Настройка камеры...")
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    camera.data.lens = 50
    camera.location = (0, -max(2.0, max_dim * 1.8), 0)
    direction = (center - camera.location).normalized()
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()
    bpy.context.scene.camera = camera

    # Удаление старого света
    print("[INFO] Удаление старого света...")
    bpy.ops.object.select_all(action='DESELECT')
    for light in [o for o in bpy.context.scene.objects if o.type == 'LIGHT']:
        light.select_set(True)
    bpy.ops.object.delete()

    # Добавление источников света
    print("[INFO] Добавление источников света...")

    def add_light(name, loc, energy):
        bpy.ops.object.light_add(type='AREA', radius=0.5)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.location = loc

    add_light("Light_Left", (-5, -5, 3), 500)
    add_light("Light_Right", (5, -5, 3), 500)
    add_light("Light_Top", (0, -5, 6), 500)

    # Настройка рендера
    print("[INFO] Настройка рендера...")
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'CPU'
    bpy.context.scene.render.resolution_x = 2048
    bpy.context.scene.render.resolution_y = 2048
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.image_settings.color_mode = 'RGBA'
    bpy.context.scene.render.film_transparent = True
    bpy.context.scene.view_settings.exposure = 1.5

    # Применение белого материала
    print("[INFO] Применение материалов...")
    for obj in mesh_objects:
        if not obj.data.materials:
            mat = bpy.data.materials.new(name="White_Material")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1)
            bsdf.inputs['Roughness'].default_value = 1.0
            bsdf.inputs['Specular'].default_value = 0.0
            bsdf.inputs['Metallic'].default_value = 0.0

            output = nodes.new('ShaderNodeOutputMaterial')
            mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            obj.data.materials.append(mat)

    # Подготовка папки
    output_dir = os.path.join(os.path.dirname(file_path), "renders")
    os.makedirs(output_dir, exist_ok=True)

    # Получение имени модели (теперь гарантированно MD5)
    model_name = os.path.splitext(os.path.basename(file_path))[0]

    # Рендеринг каждые 10 градусов (36 кадров)
    steps = 36
    total_rendered = 0
    skipped_files = 0

    for i in range(steps):
        angle = round((360 / steps) * i)
        file_name = f"{model_name}_{angle:03d}.png"
        file_path_render = os.path.join(output_dir, file_name)

        # Проверка существования файла
        if os.path.exists(file_path_render):
            print(f"[INFO] Файл уже существует: {file_name}, пропускаем рендеринг.")
            skipped_files += 1
            continue

        print(f"[INFO] Рендеринг угла {angle} градусов...")
        # Вращаем пустышку
        pivot.rotation_euler = (0, 0, -math.radians(angle))
        bpy.context.view_layer.update()

        bpy.context.scene.render.filepath = file_path_render
        try:
            bpy.ops.render.render(write_still=True)
            print(f"[INFO] Сохранено: {file_name}")
            total_rendered += 1
        except Exception as e:
            print(f"[ERROR] Ошибка рендеринга: {e}")
            return False

    # Итоговая статистика
    print(f"\n{'=' * 40}")
    print(f"Рендеринг {os.path.basename(file_path)} завершен")
    print(f"Всего файлов: {steps}")
    print(f"Отрендерено новых файлов: {total_rendered}")
    print(f"Пропущено существующих файлов: {skipped_files}")
    print(f"{'=' * 40}\n")

    return True


def process_directory(directory_path):
    """Обработка всех поддерживаемых файлов в директории"""
    print(f"\n{'#' * 50}")
    print(f"[DIR] Обработка директории: {directory_path}")
    print(f"{'#' * 50}")

    if not os.path.isdir(directory_path):
        print("[ERROR] Указанный путь не является директорией!")
        return

    # Поиск всех поддерживаемых файлов
    supported_files = []
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(('.glb', '.stl')):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path):
                supported_files.append(file_path)

    if not supported_files:
        print("[WARNING] В директории не найдено файлов .glb или .stl")
        return

    print(f"[INFO] Найдено {len(supported_files)} файлов для обработки")

    # Обработка каждого файла
    processed = 0
    skipped = 0
    for file_path in supported_files:
        try:
            if process_file(file_path):
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"[ERROR] Критическая ошибка при обработке {file_path}: {e}")
            skipped += 1

    # Итоговая статистика по директории
    print(f"\n{'#' * 50}")
    print(f"Обработка директории завершена")
    print(f"Всего файлов: {len(supported_files)}")
    print(f"Успешно обработано: {processed}")
    print(f"Пропущено/ошибки: {skipped}")
    print(f"{'#' * 50}\n")


def main():
    """Основная точка входа"""
    if len(sys.argv) < 2:
        print("[ERROR] Не указан путь к файлу или директории!")
        return

    input_path = sys.argv[-1]

    if os.path.isdir(input_path):
        process_directory(input_path)
    elif os.path.isfile(input_path):
        process_file(input_path)
    else:
        print("[ERROR] Указанный путь не существует или не является файлом/директорией!")


if __name__ == "__main__":
    main()