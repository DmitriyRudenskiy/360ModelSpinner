import bpy
import sys
import os
import math
import hashlib
import shutil
import time
from mathutils import Vector, Matrix

# ---------- Внешние библиотеки ----------
try:
    from PIL import Image as PILImage, ImageFilter, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARNING] Pillow не найдена. Обложки будут создаваться средствами Blender (медленнее).")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[WARNING] OpenCV не найден. Canny будет создан через Pillow (менее точный).")

# ---------- Настройки генерации ControlNet карт ----------
GENERATE_DEPTH = True   # Создавать карты глубины (Depth)
GENERATE_CANNY = True   # Создавать карты границ (Canny)


def calculate_md5(file_path):
    """Вычисляет MD5‑хеш файла по частям для экономии памяти."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def clean_scene():
    """Полная очистка сцены, включая данные."""
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

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

    if hasattr(bpy.data, 'orphans_purge'):
        bpy.data.orphans_purge()


def create_white_material(name="White_Material"):
    """Стандартный белый материал для рендера RGB."""
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.9, 0.9, 0.9, 1)
    bsdf.inputs['Roughness'].default_value = 0.5
    bsdf.inputs['Metallic'].default_value = 0.0
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.5
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.5

    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat


def create_depth_material(name="Depth_Mat", far_plane=10.0):
    """
    Материал, возвращающий нормализованную инвертированную глубину
    (белый – близко, чёрный – далеко). Использует Emission, поэтому
    не зависит от освещения и даёт чистую карту глубины.
    """
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Источники данных
    cam_data = nodes.new('ShaderNodeCameraData')
    math_div = nodes.new('ShaderNodeMath')
    math_div.operation = 'DIVIDE'
    math_div.inputs[1].default_value = far_plane

    math_sub = nodes.new('ShaderNodeMath')
    math_sub.operation = 'SUBTRACT'
    math_sub.inputs[0].default_value = 1.0

    color_ramp = nodes.new('ShaderNodeValToRGB')
    color_ramp.color_ramp.interpolation = 'LINEAR'
    color_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)  # чёрный
    color_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)  # белый

    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0

    output = nodes.new('ShaderNodeOutputMaterial')

    # Соединения: View Z Depth → / far → (1 - результат) → ColorRamp → Emission
    links.new(cam_data.outputs['View Z Depth'], math_div.inputs[0])
    links.new(math_div.outputs['Value'], math_sub.inputs[1])
    links.new(math_sub.outputs['Value'], color_ramp.inputs['Fac'])
    links.new(color_ramp.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], output.inputs['Surface'])

    return mat


def generate_canny_image(rgb_path, canny_path):
    """Создаёт Canny‑подобное изображение (чёрные линии на белом фоне)."""
    try:
        if HAS_CV2:
            img = cv2.imread(rgb_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError("Не удалось прочитать изображение через OpenCV")
            edges = cv2.Canny(img, 80, 200)
            # Инвертируем, чтобы линии стали чёрными (фон белый)
            inverted = 255 - edges
            cv2.imwrite(canny_path, inverted)
        elif HAS_PIL:
            with PILImage.open(rgb_path) as img:
                gray = img.convert('L')
                edges = gray.filter(ImageFilter.FIND_EDGES)
                inverted = ImageOps.invert(edges)
                inverted.save(canny_path)
        else:
            print("[WARNING] Нет ни OpenCV, ни Pillow – Canny не создан.")
            return False
        return True
    except Exception as e:
        print(f"[ERROR] Ошибка генерации Canny: {e}")
        return False


def finalize_processing(file_path, model_name, output_dir):
    """Перемещает исходный файл в ready/ и создаёт обложку из первого кадра."""
    print("[INFO] Финализация файла...")
    base_dir = os.path.dirname(file_path)
    ready_dir = os.path.join(base_dir, "ready")
    os.makedirs(ready_dir, exist_ok=True)

    zero_degree_img_name = f"{model_name}_000.png"
    zero_degree_img_path = os.path.join(output_dir, zero_degree_img_name)
    preview_img_name = f"{model_name}.jpg"
    preview_img_path = os.path.join(ready_dir, preview_img_name)

    # Создание превью
    if os.path.exists(zero_degree_img_path):
        print(f"[INFO] Создание JPG обложки...")
        if HAS_PIL:
            try:
                with PILImage.open(zero_degree_img_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((640, 640), PILImage.Resampling.LANCZOS)
                    img.save(preview_img_path, "JPEG", quality=90)
                    print(f"[INFO] Обложка сохранена (PIL): {preview_img_path}")
            except Exception as e:
                print(f"[ERROR] Ошибка Pillow: {e}. Пробуем средствами Blender.")
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
        if os.path.exists(target_file_path):
            os.remove(target_file_path)
        shutil.move(file_path, target_file_path)
        print(f"[INFO] Исходный файл перемещён в: {target_file_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Не удалось переместить исходный файл: {e}")
        return False


def process_file(file_path):
    """Основная обработка одного файла с генерацией RGB, Depth и Canny."""
    print(f"\n{'='*50}")
    print(f"[FILE] Обработка: {os.path.basename(file_path)}")
    print(f"{'='*50}")

    if not os.path.exists(file_path):
        print("[ERROR] Файл не найден!")
        return False

    # --- Этап 1: Проверка MD5 и переименование ---
    current_name = os.path.splitext(os.path.basename(file_path))[0]
    file_ext = os.path.splitext(file_path)[1]
    md5_hash = calculate_md5(file_path)

    if current_name != md5_hash:
        new_filename = f"{md5_hash}{file_ext}"
        new_path = os.path.join(os.path.dirname(file_path), new_filename)
        if new_path != file_path:
            try:
                if os.path.exists(new_path):
                    existing_md5 = calculate_md5(new_path)
                    if existing_md5 == md5_hash:
                        print("[INFO] Дубликат найден. Удаляем текущий файл, обрабатываем существующий.")
                        os.remove(file_path)
                        file_path = new_path
                    else:
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

    model_name = os.path.splitext(os.path.basename(file_path))[0]

    # --- Этап 2: Подготовка сцены ---
    clean_scene()

    # --- Этап 3: Импорт ---
    print("[INFO] Импорт файла...")
    try:
        if file_ext.lower() == '.glb':
            bpy.ops.import_scene.gltf(filepath=file_path)
        elif file_ext.lower() == '.stl':
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

    # --- Этап 4: Анализ геометрии и центрирование ---
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not mesh_objects:
        print("[ERROR] Объекты MESH не найдены.")
        return False

    min_co = Vector((float('inf'), float('inf'), float('inf')))
    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
    depsgraph = bpy.context.evaluated_depsgraph_get()

    for obj in mesh_objects:
        obj_eval = obj.evaluated_get(depsgraph)
        matrix = obj_eval.matrix_world
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

    for obj in mesh_objects:
        obj.location -= center

    # Pivot для вращения
    bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.1, location=(0, 0, 0))
    pivot = bpy.context.object
    pivot.name = "Rotation_Pivot"

    for obj in mesh_objects:
        obj.parent = pivot
        obj.matrix_parent_inverse = Matrix.Identity(4)

    # Нормализация масштаба
    target_size = 2.0
    if max_dim > 0:
        scale_factor = target_size / max_dim
        pivot.scale = (scale_factor, scale_factor, scale_factor)
        max_dim = target_size

    # --- Этап 5: Материалы ---
    white_mat = create_white_material("Render_White")
    # Сохраняем оригинальные материалы для последующего восстановления
    original_materials = {}
    for obj in mesh_objects:
        original_materials[obj.name] = [slot.material for slot in obj.material_slots]

    # Назначаем белый материал, если у объекта нет материалов или это STL
    for obj in mesh_objects:
        if file_ext.lower() == '.stl':
            obj.data.materials.clear()
            obj.data.materials.append(white_mat)
        elif not obj.data.materials:
            obj.data.materials.append(white_mat)

    # --- Этап 6: Камера и освещение ---
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    camera.data.lens = 50

    fov = 2 * math.atan(36 / (2 * camera.data.lens))
    camera_distance = (max_dim * 0.6) / math.tan(fov / 2)
    camera_distance = max(camera_distance, 3.5)

    # Определяем far_plane для глубины (с запасом)
    far_plane = camera_distance + max_dim * 1.2
    camera.data.clip_end = far_plane

    # Материал для глубины (создаётся один раз, far_plane фиксировано)
    depth_mat = create_depth_material("Depth_Mat", far_plane) if GENERATE_DEPTH else None

    def add_light(name, loc, energy, size=1.0):
        bpy.ops.object.light_add(type='AREA', radius=size)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.location = loc
        direction = (Vector((0, 0, 0)) - Vector(loc)).normalized()
        rot_quat = direction.to_track_quat('-Z', 'Y')
        light.rotation_euler = rot_quat.to_euler()

    add_light("Key", (-3, -camera_distance, 4), 300, size=2.0)
    add_light("Fill", (4, -camera_distance * 0.5, 2), 150, size=2.0)
    add_light("Rim", (0, camera_distance * 0.5, 5), 200, size=1.5)

    # --- Этап 7: Настройки рендера ---
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'

    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        has_gpu = False
        for dev_type in ['METAL', 'OPTIX', 'CUDA', 'HIP', 'ONEAPI']:
            try:
                prefs.compute_device_type = dev_type
                if any(device.type in ['GPU', 'OPTIX', 'CUDA', 'METAL', 'HIP', 'ONEAPI']
                       for device in prefs.get_devices()):
                    scene.cycles.device = 'GPU'
                    print(f"[INFO] Устройство рендера: {dev_type}")
                    has_gpu = True
                    break
            except TypeError:
                continue
        if not has_gpu:
            scene.cycles.device = 'CPU'
            print("[INFO] GPU не найден, используется CPU.")
    except Exception as e:
        print(f"[WARNING] Ошибка настройки рендера: {e}. Используем CPU.")
        scene.cycles.device = 'CPU'

    scene.cycles.samples = 64
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 2048
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'

    # --- Этап 8: Рендеринг RGB и Depth ---
    output_dir = os.path.join(os.path.dirname(file_path), "renders")
    os.makedirs(output_dir, exist_ok=True)

    depth_dir = os.path.join(os.path.dirname(file_path), "renders_depth") if GENERATE_DEPTH else None
    canny_dir = os.path.join(os.path.dirname(file_path), "renders_canny") if GENERATE_CANNY else None
    if depth_dir:
        os.makedirs(depth_dir, exist_ok=True)
    if canny_dir:
        os.makedirs(canny_dir, exist_ok=True)

    scene.camera = camera

    camera_angles = [-30, -15, 0, 15, 30]
    steps = 36
    total_rgb = 0
    total_depth = 0

    for cam_angle in camera_angles:
        # Позиционируем камеру
        phi = math.radians(cam_angle)
        cam_y = -camera_distance * math.cos(phi)
        cam_z = camera_distance * math.sin(phi)
        camera.location = (0, cam_y, cam_z)
        direction = (Vector((0, 0, 0)) - camera.location).normalized()
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        for i in range(steps):
            rot_angle = round((360 / steps) * i)
            pivot.rotation_euler = (0, 0, math.radians(rot_angle))
            bpy.context.view_layer.update()

            # Формирование имён файлов
            if cam_angle == 0:
                base_name = f"{model_name}_{rot_angle:03d}"
            else:
                suffix = f"_e{cam_angle:+d}"
                base_name = f"{model_name}_{rot_angle:03d}{suffix}"

            rgb_path = os.path.join(output_dir, f"{base_name}.png")
            depth_path = os.path.join(depth_dir, f"{base_name}.png") if depth_dir else None

            # --- Рендер глубины (если требуется и файл отсутствует) ---
            if depth_dir and not os.path.exists(depth_path):
                # Подменяем материал на depth_mat
                for obj in mesh_objects:
                    obj.data.materials.clear()
                    obj.data.materials.append(depth_mat)
                # Уменьшаем сэмплы для ускорения (глубина не требует качества)
                old_samples = scene.cycles.samples
                scene.cycles.samples = 1
                scene.render.filepath = depth_path
                try:
                    bpy.ops.render.render(write_still=True)
                    total_depth += 1
                except Exception as e:
                    print(f"[ERROR] Ошибка рендера глубины: {e}")
                finally:
                    scene.cycles.samples = old_samples
                # Возвращаем исходные материалы (или белый)
                for obj in mesh_objects:
                    obj.data.materials.clear()
                    mats = original_materials.get(obj.name, [])
                    if mats and all(m is not None for m in mats):
                        for m in mats:
                            obj.data.materials.append(m)
                    else:
                        obj.data.materials.append(white_mat)

            # --- Рендер RGB (если файл отсутствует) ---
            if not os.path.exists(rgb_path):
                scene.render.filepath = rgb_path
                try:
                    bpy.ops.render.render(write_still=True)
                    total_rgb += 1
                except Exception as e:
                    print(f"[ERROR] Ошибка рендера RGB: {e}")

    print(f"[INFO] Рендеринг завершён. RGB: {total_rgb}, Depth: {total_depth}")

    # --- Этап 9: Постобработка – Canny ---
    if canny_dir:
        os.makedirs(canny_dir, exist_ok=True)
        processed_canny = 0
        for filename in os.listdir(output_dir):
            if not filename.lower().endswith('.png'):
                continue
            rgb_full = os.path.join(output_dir, filename)
            canny_full = os.path.join(canny_dir, filename)
            if not os.path.exists(canny_full):
                if generate_canny_image(rgb_full, canny_full):
                    processed_canny += 1
        print(f"[INFO] Canny изображений создано: {processed_canny}")

    # --- Этап 10: Финализация (перемещение исходника) ---
    if not finalize_processing(file_path, model_name, output_dir):
        return False

    return True


def process_directory(directory_path):
    """Обработка всех .glb/.stl файлов в папке."""
    supported_files = []
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(('.glb', '.stl')):
            supported_files.append(os.path.join(directory_path, filename))

    if not supported_files:
        print("[WARNING] Поддерживаемые файлы не найдены.")
        return

    print(f"[INFO] Найдено файлов: {len(supported_files)}")
    for file_path in supported_files:
        try:
            process_file(file_path)
        except Exception as e:
            print(f"[CRITICAL] Ошибка обработки {file_path}: {e}")
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