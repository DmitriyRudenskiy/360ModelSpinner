import os
from PIL import Image
import argparse


def is_dark_pixel(r, g, b, tolerance=25, max_val=120):
    """Проверяет, является ли пиксель темным (серым/черным)"""
    if abs(r - g) > tolerance or abs(r - b) > tolerance or abs(g - b) > tolerance:
        return False
    # Проверяем, что все компоненты в пределах max_val
    return r <= max_val and g <= max_val and b <= max_val


def find_crop_height(img):
    """Определяет высоту обрезки, находя темную плашку внизу"""
    width, height = img.size
    crop_y = height

    # Проверяем строки снизу вверх
    for y in range(height - 1, -1, -1):
        dark_pixels = 0
        for x in range(width):
            r, g, b = img.getpixel((x, y))
            if is_dark_pixel(r, g, b):
                dark_pixels += 1

        # Если 70% пикселей строки темные - считаем строку частью плашки
        if dark_pixels / width >= 0.7:
            continue
        else:
            crop_y = y + 1
            break

    return crop_y


def process_images(directory):
    """Обрабатывает все изображения в указанной директории"""
    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    total_processed = 0
    cropped_count = 0
    skipped_count = 0
    crop_percentages = []

    for filename in os.listdir(directory):
        if not filename.lower().endswith(supported_formats):
            continue

        filepath = os.path.join(directory, filename)

        try:
            with Image.open(filepath) as img:
                # Конвертируем в RGB для единообразной обработки
                img = img.convert('RGB')
                original_width, original_height = img.size
                crop_y = find_crop_height(img)

                # Обрезаем только если найдена плашка (минимум 20 пикселей)
                if crop_y < img.height and (img.height - crop_y) > 20:
                    cropped_img = img.crop((0, 0, img.width, crop_y))
                    new_width, new_height = cropped_img.size

                    # Рассчитываем процент обрезанной высоты
                    cropped_pixels = original_height - crop_y
                    crop_percentage = (cropped_pixels / original_height) * 100
                    crop_percentages.append(crop_percentage)

                    new_filename = f"crop_{filename}"
                    new_filepath = os.path.join(directory, new_filename)
                    cropped_img.save(new_filepath)
                    print(
                        f"Обработано: {filename} -> {new_filename} | Размер: {original_width}x{original_height} -> {new_width}x{new_height} | Обрезано: {cropped_pixels}px ({crop_percentage:.2f}%)")
                    cropped_count += 1
                else:
                    print(f"Пропущено (нет плашки): {filename} | Размер: {original_width}x{original_height}")
                    skipped_count += 1

                total_processed += 1

        except Exception as e:
            print(f"Ошибка при обработке {filename}: {str(e)}")

    # Вывод сводной аналитики
    if total_processed > 0:
        print("\n" + "=" * 50)
        print("СВОДНАЯ АНАЛИТИКА ПО ОБРЕЗКЕ ИЗОБРАЖЕНИЙ")
        print("=" * 50)
        print(f"Всего обработано изображений: {total_processed}")
        print(f"Успешно обрезано: {cropped_count} ({cropped_count / total_processed:.1%})")
        print(f"Пропущено (без плашки): {skipped_count} ({skipped_count / total_processed:.1%})")

        if cropped_count > 0:
            min_percent = min(crop_percentages)
            max_percent = max(crop_percentages)
            avg_percent = sum(crop_percentages) / cropped_count

            print(f"\nСтатистика по обрезанным изображениям:")
            print(f"Минимальный процент обрезки: {min_percent:.2f}%")
            print(f"Максимальный процент обрезки: {max_percent:.2f}%")
            print(f"Средний процент обрезки: {avg_percent:.2f}%")

            # Подсчет конкретных значений с округлением до 1 знака после запятой
            percentage_counts = {}
            for p in crop_percentages:
                # Округляем до 1 знака после запятой для группировки
                rounded_p = round(p, 1)
                percentage_counts[rounded_p] = percentage_counts.get(rounded_p, 0) + 1

            # Сортируем по процентам
            sorted_percentages = sorted(percentage_counts.items())

            print("\nРаспределение по конкретным процентам обрезки:")
            for percent, count in sorted_percentages:
                percentage_of_total = (count / cropped_count) * 100
                print(f"  {percent:.1f}%: {count} изображений ({percentage_of_total:.1f}%)")
        else:
            print("\nНет обрезанных изображений для анализа.")
    else:
        print("\nНе обработано ни одного изображения.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Обрезка темной плашки внизу изображений')
    parser.add_argument('directory', type=str, help='Директория с изображениями')
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Ошибка: '{args.directory}' не является директорией")
        exit(1)

    process_images(args.directory)