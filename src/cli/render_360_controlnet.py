import bpy
import sys
import os
import math
import hashlib
import shutil
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
    """Надежная очистка сцены. Удаляет все объекты и орфанные данные."""
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for block in bpy.data.meshes:
        if block.users == 0: bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0: bpy.data.materials.remove(block)
    for block in bpy.data.textures:
        if block.users == 0: bpy.data.textures.remove(block)
    for block in bpy.data.images:
        if block.users == 0: bpy.data.images.remove(block)
    for block in bpy.data.lights:
        if block.users == 0: bpy.data.lights.remove(block)
    for block in bpy.data.cameras:
        if block.users == 0: bpy.data.cameras.remove(block)

    if hasattr(bpy.data, 'orphans_purge'):
        bpy.data.orphans_purge()


def create_flat_material(name="Flat_White_Canny"):
    """Создает плоский Emission материал без теней и бликов (Идеально для Canny)."""
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs['Strength'].default_value = 1.0

    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat


def create_depth_material(name="Depth_Material", cam_dist=3.5, obj_dim=2.0):
    """
    Создает материал ОТНОСИТЕЛЬНОЙ глубины (как Depth Anything V2).
    Ближайшая точка = 1.0 (Белый), Дальняя точка = 0.0 (Черный), Фон = 0.0.
    """
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    camera_data = nodes.new('ShaderNodeCameraData')

    # View Z Depth в Blender отрицательная для объектов перед камерой.
    # Инвертируем знак, чтобы получить положительное расстояние
    math1 = nodes.new('ShaderNodeMath')
    math1.operation = 'MULTIPLY'
    math1.inputs[1].default_value = -1.0

    # Вычитаем максимальную дистанцию (самая дальняя точка объекта становится 0)
    max_dist = cam_dist + (obj_dim / 2.0)
    math2 = nodes.new('ShaderNodeMath')
    math2.operation = 'SUBTRACT'
    math2.inputs[1].default_value = max_dist

    # Снова инвертируем: ближняя точка становится положительной, дальняя 0
    math3 = nodes.new('ShaderNodeMath')
    math3.operation = 'MULTIPLY'
    math3.inputs[1].default_value = -1.0

    # Делим на толщину объекта (диаметр), нормализуя дальность от 0.0 до 1.0
    math4 = nodes.new('ShaderNodeMath')
    math4.operation = 'DIVIDE'
    math4.inputs[1].default_value = obj_dim
    math4.use_clamp = True  # Отсекаем все что вышло за пределы 0-1 (фон и т.д.)

    emission = nodes.new('ShaderNodeEmission')
    output = nodes.new('ShaderNodeOutputMaterial')

    links.new(camera_data.outputs['View Z Depth'], math1.inputs[0])
    links.new(math1.outputs[0], math2.inputs[0])
    links.new(math2.outputs[0], math3.inputs[0])
    links.new(math3.outputs[0], math4.inputs[0])
    links.new(math4.outputs[0], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat


def setup_compositor(cam_dist=3.5, obj_dim=2.0):
    """Настройка композитора для Canny и Relative Depth."""
    scene = bpy.context.scene

    tree = None
    if hasattr(scene, 'compositor'):
        tree = getattr(scene, 'compositor', None)
    elif hasattr(scene, 'node_tree'):
        tree = getattr(scene, 'node_tree', None)

    if not isinstance(tree, bpy.types.NodeTree):
        print("[WARNING] Compositor Node Tree недоступен. Используем рендер в два прохода.")
        return None

    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    render_layers = nodes.new('CompositorNodeRLayers')

    out_canny = nodes.new('CompositorNodeOutputFile')
    out_canny.name = "OutputCanny"
    out_canny.format.file_format = 'PNG'
    out_canny.format.color_mode = 'RGBA'
    out_canny.format.color_depth = '8'

    out_depth = nodes.new('CompositorNodeOutputFile')
    out_depth.name = "OutputDepth"
    out_depth.format.file_format = 'PNG'
    out_depth.format.color_mode = 'RGB'
    out_depth.format.color_depth = '16'

    # --- Относительная Depth Математика ---
    max_dist = cam_dist + (obj_dim / 2.0)

    math1 = nodes.new('CompositorNodeMath')
    math1.operation = 'MULTIPLY'
    math1.inputs[1].default_value = -1.0

    math2 = nodes.new('CompositorNodeMath')
    math2.operation = 'SUBTRACT'
    math2.inputs[1].default_value = max_dist

    math3 = nodes.new('CompositorNodeMath')
    math3.operation = 'MULTIPLY'
    math3.inputs[1].default_value = -1.0

    math4 = nodes.new('CompositorNodeMath')
    math4.operation = 'DIVIDE'
    math4.inputs[1].default_value = obj_dim
    math4.use_clamp = True

    # Маска для фона: умножаем результат на Альфа-канал, чтобы фон стал чисто черным
    mix_depth = nodes.new('CompositorNodeMixRGB')
    mix_depth.blend_type = 'MULTIPLY'
    mix_depth.inputs[0].default_value = 1.0

    # Связи
    links.new(render_layers.outputs['Image'], out_canny.inputs[0])

    links.new(render_layers.outputs['Depth'], math1.inputs[0])
    links.new(math1.outputs[0], math2.inputs[0])
    links.new(math2.outputs[0], math3.inputs[0])
    links.new(math3.outputs[0], math4.inputs[0])

    links.new(math4.outputs[0], mix_depth.inputs[1])  # Color 1 (Наша глубина)
    links.new(render_layers.outputs['Alpha'], mix_depth.inputs[2])  # Color 2 (Маска)
    links.new(mix_depth.outputs[0], out_depth.inputs[0])

    return out_canny, out_depth


def finalize_processing(file_path, model_name, output_dir):
    """Перемещает оригинальный файл и создает обложку."""
    print("[INFO] Финализация файла...")
    base_dir = os.path.dirname(file_path)
    ready_dir = os.path.join(base_dir, "ready")
    os.makedirs(ready_dir, exist_ok=True)

    zero_degree_img_name = f"{model_name}_000_canny.png"
    zero_degree_img_path = os.path.join(output_dir, zero_degree_img_name)
    preview_img_name = f"{model_name}.jpg"
    preview_img_path = os.path.join(ready_dir, preview_img_name)

    if os.path.exists(zero_degree_img_path):
        print(f"[INFO] Создание JPG обложки...")
        if HAS_PIL:
            try:
                with PILImage.open(zero_degree_img_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((640, 640), PILImage.Resampling.LANCZOS)
                    img.save(preview_img_path, "JPEG", quality=90)
            except Exception as e:
                print(f"[ERROR] Ошибка Pillow: {e}.")

        if not HAS_PIL or not os.path.exists(preview_img_path):
            try:
                img = bpy.data.images.load(zero_degree_img_path)
                img.scale(640, 640)
                img.filepath_raw = preview_img_path
                img.file_format = 'JPEG'
                img.save()
                bpy.data.images.remove(img)
            except Exception as e:
                print(f"[ERROR] Не удалось сохранить обложку: {e}")

    try:
        target_file_path = os.path.join(ready_dir, os.path.basename(file_path))
        if os.path.exists(target_file_path):
            os.remove(target_file_path)
        shutil.move(file_path, target_file_path)
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
                        os.remove(file_path)
                        file_path = new_path
                    else:
                        new_path = os.path.join(os.path.dirname(file_path), f"{new_filename}.new")
                        os.rename(file_path, new_path)
                        file_path = new_path
                else:
                    os.rename(file_path, new_path)
                    file_path = new_path
            except Exception as e:
                print(f"[ERROR] Ошибка переименования: {e}")
                return False

    model_name = os.path.splitext(os.path.basename(file_path))[0]
    clean_scene()

    print(f"[INFO] Импорт файла...")
    try:
        if file_ext.lower() == '.glb':
            bpy.ops.import_scene.gltf(filepath=file_path)
        elif file_ext.lower() == '.stl':
            try:
                bpy.ops.wm.stl_import(filepath=file_path)
            except AttributeError:
                bpy.ops.import_mesh.stl(filepath=file_path)
        else:
            return False
    except Exception as e:
        print(f"[ERROR] Ошибка импорта: {e}")
        return False

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not mesh_objects:
        return False

    min_co = Vector((float('inf'), float('inf'), float('inf')))
    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
    for obj in mesh_objects:
        obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        matrix = obj.matrix_world
        for corner in obj.bound_box:
            world_corner = matrix @ Vector(corner)
            for i in range(3):
                min_co[i] = min(min_co[i], world_corner[i])
                max_co[i] = max(max_co[i], world_corner[i])

    center = (min_co + max_co) / 2
    size = max_co - min_co
    max_dim = max(size.x, size.y, size.z)

    for obj in mesh_objects:
        obj.location -= center

    bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.1, location=(0, 0, 0))
    pivot = bpy.context.object
    pivot.name = "Rotation_Pivot"

    for obj in mesh_objects:
        obj.parent = pivot
        obj.matrix_parent_inverse = Matrix.Identity(4)

    target_size = 2.0
    if max_dim > 0:
        scale_factor = target_size / max_dim
        pivot.scale = (scale_factor, scale_factor, scale_factor)
        max_dim = target_size

    flat_mat = create_flat_material("Flat_White_Canny")

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    camera.data.lens = 50

    fov = 2 * math.atan(36 / (2 * camera.data.lens))
    camera_distance = (max_dim * 0.6) / math.tan(fov / 2)
    camera_distance = max(camera_distance, 3.5)

    camera.data.clip_start = 0.1
    camera.data.clip_end = camera_distance * 2

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.render.use_compositing = True

    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        has_gpu = False
        for dev_type in ['METAL', 'OPTIX', 'CUDA', 'HIP', 'ONEAPI']:
            try:
                prefs.compute_device_type = dev_type
                if any(device.type in ['GPU', 'OPTIX', 'CUDA', 'METAL', 'HIP', 'ONEAPI'] for device in
                       prefs.get_devices()):
                    scene.cycles.device = 'GPU'
                    has_gpu = True
                    break
            except TypeError:
                continue
        if not has_gpu: scene.cycles.device = 'CPU'
    except Exception:
        scene.cycles.device = 'CPU'

    scene.cycles.samples = 16
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'

    if 'World' not in bpy.data.worlds:
        world = bpy.data.worlds.new('World')
    else:
        world = bpy.data.worlds['World']

    w_tree = world.node_tree if hasattr(world, 'node_tree') else None
    if w_tree:
        w_nodes = w_tree.nodes
        w_links = w_tree.links
        w_nodes.clear()
        bg = w_nodes.new('ShaderNodeBackground')
        bg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs['Strength'].default_value = 1.0
        out = w_nodes.new('ShaderNodeOutputWorld')
        w_links.new(bg.outputs['Background'], out.inputs['Surface'])

    bpy.context.view_layer.use_pass_z = True  # Включаем Z-Depth вместо Mist

    # Передаем дистанцию и размер объекта для точной калибровки глубины
    compositor_outputs = setup_compositor(cam_dist=camera_distance, obj_dim=max_dim)
    use_compositor = compositor_outputs is not None

    depth_mat = create_depth_material("Depth_Material", cam_dist=camera_distance, obj_dim=max_dim)

    for obj in mesh_objects:
        obj.data.materials.clear()
        obj.data.materials.append(flat_mat)

    output_dir = os.path.join(os.path.dirname(file_path), "renders")
    os.makedirs(output_dir, exist_ok=True)

    camera_angles = [-30, -15, 0, 15, 30]
    steps = 36
    total_rendered = 0

    for cam_angle in camera_angles:
        phi = math.radians(cam_angle)
        cam_y = -camera_distance * math.cos(phi)
        cam_z = camera_distance * math.sin(phi)
        camera.location = (0, cam_y, cam_z)

        direction = (Vector((0, 0, 0)) - camera.location).normalized()
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        for i in range(steps):
            rot_angle = round((360 / steps) * i)

            if cam_angle == 0:
                base_name = f"{model_name}_{rot_angle:03d}"
            else:
                base_name = f"{model_name}_{rot_angle:03d}_e{cam_angle:+d}"

            canny_path = os.path.join(output_dir, f"{base_name}_canny.png")
            depth_path = os.path.join(output_dir, f"{base_name}_depth.png")

            if os.path.exists(canny_path) and os.path.exists(depth_path):
                continue

            pivot.rotation_euler = (0, 0, math.radians(rot_angle))
            bpy.context.view_layer.update()

            if use_compositor:
                out_canny, out_depth = compositor_outputs
                out_canny.base_path = output_dir
                out_canny.file_slots[0].path = f"{base_name}_canny"
                out_depth.base_path = output_dir
                out_depth.file_slots[0].path = f"{base_name}_depth"

                try:
                    bpy.ops.render.render(write_still=False)
                    total_rendered += 1
                except Exception as e:
                    print(f"[ERROR] Ошибка рендера композитора: {e}")
            else:
                try:
                    for obj in mesh_objects: obj.data.materials[0] = flat_mat
                    scene.render.filepath = canny_path
                    bpy.ops.render.render(write_still=True)

                    for obj in mesh_objects: obj.data.materials[0] = depth_mat
                    scene.render.filepath = depth_path
                    bpy.ops.render.render(write_still=True)

                    total_rendered += 2
                except Exception as e:
                    print(f"[ERROR] Ошибка резервного рендера: {e}")

    print(f"[INFO] Рендеринг завершен. Изображений сохранено: {total_rendered}")
    if not finalize_processing(file_path, model_name, output_dir): return False
    return True


def process_directory(directory_path):
    supported_files = []
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(('.glb', '.stl')):
            supported_files.append(os.path.join(directory_path, filename))

    if not supported_files: return
    for file_path in supported_files:
        try:
            process_file(file_path)
        except Exception as e:
            print(f"[CRITICAL] Ошибка: {e}")
            import traceback
            traceback.print_exc()


def main():
    if len(sys.argv) < 2: return
    input_path = sys.argv[-1]
    if os.path.isdir(input_path):
        process_directory(input_path)
    elif os.path.isfile(input_path):
        process_file(input_path)


if __name__ == "__main__":
    main()