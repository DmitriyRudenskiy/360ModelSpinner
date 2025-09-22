import sys
import os
import argparse
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description='Process PNG images with alpha channel.')
    parser.add_argument('-s', '--source', required=True, help='Input PNG file path')
    parser.add_argument('-d', '--destination', help='Output JPEG file path (default: input.jpg)')
    parser.add_argument('-w', '--width', type=int, default=768, help='Target width in pixels (default: 768)')
    parser.add_argument('-H', '--height', type=int, default=1024, help='Target height in pixels (default: 1024)')
    parser.add_argument('-f', '--force', action='store_true', help='Overwrite output file if exists')

    args = parser.parse_args()

    # Проверка корректности размеров
    if args.width <= 0 or args.height <= 0:
        print("Error: Width and height must be positive integers.")
        sys.exit(1)

    # Определение выходного пути
    if not args.destination:
        base_name = os.path.splitext(args.source)[0]
        output_path = f"{base_name}.jpg"
        print(base_name);
        print(output_path);
    else:
        output_path = args.destination

    # Проверка расширений файлов
    if not args.source.lower().endswith('.png'):
        print("Error: Input file must be a PNG image (extension .png).")
        sys.exit(1)

    if not output_path.lower().endswith(('.jpg', '.jpeg')):
        print("Error: Output file must be a JPEG image (extension .jpg or .jpeg).")
        sys.exit(1)

    # Проверка существования выходного файла
    if os.path.exists(output_path):
        if not args.force:
            print(f"Error: Output file '{output_path}' already exists.")
            print("Use -f or --force to overwrite.")
            sys.exit(1)
        else:
            print(f"Warning: Overwriting existing file '{output_path}'")

    try:
        # Открытие изображения
        with Image.open(args.source) as img:
            # Проверка наличия альфа-канала
            if 'A' not in img.mode:
                print("Error: Input image must have an alpha channel (RGBA format).")
                print(f"Current mode: {img.mode}")
                sys.exit(1)

            # Получение bounding box по альфа-каналу
            bbox = img.getbbox()
            if bbox is None:
                print("Error: The image is fully transparent (no visible content).")
                sys.exit(1)

            # Обрезка по bounding box
            cropped = img.crop(bbox)

            # Масштабирование с сохранением пропорций
            orig_width, orig_height = cropped.size
            target_width, target_height = args.width, args.height

            # Расчёт коэффициента масштабирования
            scale_ratio = min(target_width / orig_width, target_height / orig_height)
            new_width = int(orig_width * scale_ratio)
            new_height = int(orig_height * scale_ratio)

            # Изменение размера с высоким качеством
            resized = cropped.resize(
                (new_width, new_height),
                Image.LANCZOS
            )

            # Создание серого фона
            background = Image.new('RGB', (target_width, target_height), (128, 128, 128))

            # Расчёт позиции для центрирования
            x = (target_width - new_width) // 2
            y = (target_height - new_height) // 2

            # Вставка изображения с учётом альфа-канала
            background.paste(resized, (x, y), resized)

            # Сохранение результата
            background.save(output_path, 'JPEG', quality=93)
            print(f"Successfully saved result to {output_path} ({target_width}x{target_height})")

    except FileNotFoundError:
        print(f"Error: Input file '{args.source}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()