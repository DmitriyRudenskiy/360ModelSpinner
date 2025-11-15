import os
import argparse
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description='Crop images in a directory.')
    parser.add_argument('directory', type=str, help='Directory containing images to crop')
    args = parser.parse_args()

    directory = args.directory

    # Проверка существования директории
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        return

    # Поддерживаемые графические форматы
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff')

    for filename in os.listdir(directory):
        # Пропускаем файлы с префиксом crop_ и не графические файлы
        if filename.startswith('crop_') or not filename.lower().endswith(image_extensions):
            continue

        filepath = os.path.join(directory, filename)
        try:
            with Image.open(filepath) as img:
                width, height = img.size

                # Определение ориентации
                if width > height:
                    crop_percent = 9.1
                elif height > width:
                    crop_percent = 6.25
                else:
                    crop_percent = 4.8

                # Вычисление высоты обрезки
                crop_amount = round(height * (crop_percent / 100))
                new_height = height - crop_amount

                # Проверка допустимой высоты
                if new_height <= 0:
                    print(f"⚠️  Image {filename} is too small to crop. Skipping.")
                    continue

                # Обрезка изображения (оставляем верхнюю часть)
                cropped_img = img.crop((0, 0, width, new_height))

                # Сохранение обработанного изображения
                new_filename = f"crop_{filename}"
                new_filepath = os.path.join(directory, new_filename)
                cropped_img.save(new_filepath)

                print(f"✅ Cropped {filename} -> {new_filename} "
                      f"({width}x{height} → {width}x{new_height}, "
                      f"removed {crop_amount}px bottom)")

        except Exception as e:
            print(f"❌ Error processing {filename}: {str(e)}")


if __name__ == "__main__":
    main()