import argparse
import os
import sys
from PIL import Image
from typing import Tuple, Optional

# Константы
RESOLUTIONS = (
    (640, 1536),
    (768, 1344),
    (832, 1216),
    (896, 1152),
    (1024, 1024),
    (1152, 896),
    (1216, 832),
    (1344, 768),
    (1536, 640)
)

BACKGROUND_COLORS = {
    "ultra_light": (240, 240, 240),
    "light": (128, 128, 128),
    "medium": (64, 64, 64),
    "dark": (32, 32, 32),
    "very_dark": (16, 16, 12)
}


def validate_input(source_path: str) -> None:
    """Проверяет корректность входного файла."""
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Input file not found: {source_path}")

    if not source_path.lower().endswith(".png"):
        raise ValueError("Input file must be a PNG image (extension .png)")


def validate_output(output_path: str, force: bool) -> None:
    """Проверяет возможность записи выходного файла."""
    if os.path.exists(output_path) and not force:
        raise FileExistsError(
            f"Output file already exists: {output_path}\n"
            "Use -f or --force to overwrite."
        )


def process_image(
        source_path: str,
        output_path: str,
        target_size: Tuple[int, int],
        background_color: Tuple[int, int, int],
        force: bool
) -> None:
    """
    Обрабатывает изображение: обрезка, масштабирование, сохранение.

    Args:
        source_path: Путь к исходному PNG-файлу
        output_path: Путь для сохранения результата
        target_size: Целевой размер (ширина, высота)
        background_color: Цвет фона в формате RGB
        force: Разрешить перезапись существующих файлов

    Raises:
        Exception: При возникновении ошибок обработки
    """
    # Проверки и подготовка
    validate_input(source_path)
    validate_output(output_path, force)

    target_width, target_height = target_size

    try:
        with Image.open(source_path) as img:
            # Проверка формата
            if "A" not in img.mode:
                raise ValueError(
                    f"Input image must have alpha channel (RGBA). Current mode: {img.mode}"
                )

            # Проверка содержимого
            if img.getbbox() is None:
                raise ValueError("Image is fully transparent (no visible content)")

            # Обрезка и масштабирование
            cropped = img.crop(img.getbbox())
            orig_width, orig_height = cropped.size
            scale_ratio = min(
                target_width / orig_width,
                target_height / orig_height
            )
            new_size = (
                int(orig_width * scale_ratio),
                int(orig_height * scale_ratio)
            )
            resized = cropped.resize(new_size, Image.LANCZOS)

            # Создание фона и размещение изображения
            background = Image.new("RGB", (target_width, target_height), background_color)
            x = (target_width - new_size[0]) // 2
            y = (target_height - new_size[1]) // 2
            background.paste(resized, (x, y), resized)

            # Сохранение
            background.save(output_path, "JPEG", quality=93)
            print(f"✓ Saved: {output_path} | Size: {target_width}x{target_height}")

    except Exception as e:
        raise RuntimeError(f"Processing error: {str(e)}") from e


def get_output_path(
        source_path: str,
        output_arg: Optional[str],
        width: int,
        height: int
) -> str:
    """Генерирует выходной путь для изображения."""
    if output_arg:
        if os.path.isdir(output_arg):
            base_name = os.path.splitext(os.path.basename(source_path))[0]
            return os.path.join(output_arg, f"{base_name}_{width}x{height}.jpg")
        return output_arg

    # Замена расширения на .jpg
    return os.path.splitext(source_path)[0] + ".jpg"


def main():
    parser = argparse.ArgumentParser(
        description="Convert PNG images with alpha channel to JPEG with background",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "-s", "--source",
        required=True,
        help="Input PNG file path"
    )
    parser.add_argument(
        "-d", "--destination",
        help="Output path (file or directory). If directory, generates name automatically"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=1,
        help="Index in RESOLUTIONS array (0-8)",
        choices=range(len(RESOLUTIONS))
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite output file if exists"
    )
    parser.add_argument(
        "--background",
        choices=list(BACKGROUND_COLORS.keys()),
        default="ultra_light",
        help="Background color scheme"
    )

    args = parser.parse_args()

    # Определение цвета фона
    background_color = BACKGROUND_COLORS[args.background]

    # Обработка изображения
    source_path = os.path.abspath(args.source)
    width, height = RESOLUTIONS[args.size]
    output_path = get_output_path(
        source_path,
        args.destination,
        width,
        height
    )

    try:
        print(background_color)

        process_image(
            source_path,
            output_path,
            (width, height),
            background_color,
            args.force
        )
    except Exception as e:
        print(f"✗ Failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()