import sys
import argparse
import logging
from enum import Enum
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

from PIL import Image

# Попытка импорта tqdm для прогресс-бара (опционально)
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class SizePreset(Enum):
    """Предопределённые пары ширина × высота."""
    SIZE_768x1376 = (768, 1376)
    SIZE_848x1264 = (848, 1264)
    SIZE_896x1200 = (896, 1200)
    SIZE_1024x1024 = (1024, 1024)
    SIZE_1200x896 = (1200, 896)
    SIZE_1264x848 = (1264, 848)
    SIZE_1376x768 = (1376, 768)

    @property
    def width(self) -> int:
        return self.value[0]

    @property
    def height(self) -> int:
        return self.value[1]

    @classmethod
    def from_string(cls, name: str):
        """Получить член enum по строковому имени (без учёта регистра)."""
        name_lower = name.lower()
        for member in cls:
            if member.name.lower() == name_lower:
                return member
        raise argparse.ArgumentTypeError(
            f"Недопустимое имя пресета '{name}'. Допустимые: {', '.join(cls.__members__.keys())}"
        )


class ResampleFilter(Enum):
    """Доступные фильтры ресамплинга Pillow."""
    NEAREST = Image.NEAREST
    BILINEAR = Image.BILINEAR
    BICUBIC = Image.BICUBIC
    LANCZOS = Image.LANCZOS
    HAMMING = Image.HAMMING
    BOX = Image.BOX

    @classmethod
    def from_string(cls, name: str):
        name_upper = name.upper()
        if name_upper in cls.__members__:
            return cls.__members__[name_upper]
        raise argparse.ArgumentTypeError(
            f"Неизвестный фильтр '{name}'. Допустимые: {', '.join(cls.__members__.keys())}"
        )


def parse_color(color_str: str) -> Tuple[int, int, int]:
    """Преобразует строку 'R,G,B' в кортеж целых чисел."""
    try:
        parts = color_str.split(',')
        if len(parts) != 3:
            raise ValueError
        r, g, b = map(int, parts)
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError
        return r, g, b
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Цвет должен быть в формате 'R,G,B' (0-255), получено: '{color_str}'"
        )


def find_png_files(root_dir: Path, recursive: bool) -> List[Path]:
    """Возвращает список всех .png файлов в директории (с рекурсивным обходом, если нужно)."""
    if recursive:
        return [p for p in root_dir.rglob('*.png') if p.is_file()]
    else:
        return [p for p in root_dir.glob('*.png') if p.is_file()]


def process_single_image(
        source_path: Path,
        output_path: Path,
        target_width: int,
        target_height: int,
        quality: int,
        resample_filter: int,
        bg_color: Tuple[int, int, int],
        overwrite: bool
) -> Tuple[str, bool]:
    """
    Обрабатывает одно изображение.
    Возвращает кортеж: (сообщение, флаг успеха).
    """
    if not overwrite and output_path.exists():
        return f"ПРОПУЩЕН (уже существует): {output_path.name}", False

    try:
        with Image.open(source_path) as img:
            # Определяем, есть ли альфа-канал
            has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

            if has_alpha:
                # Конвертируем в RGBA для корректной работы с прозрачностью
                img = img.convert('RGBA')
                bbox = img.getbbox()
                if bbox is None:
                    return f"ПРОПУЩЕН (полностью прозрачный): {source_path.name}", False
                cropped = img.crop(bbox)
            else:
                # Для изображений без прозрачности bbox — это всё изображение
                bbox = (0, 0, img.width, img.height)
                cropped = img.copy()

            orig_width, orig_height = cropped.size

            # Расчёт коэффициента масштабирования
            scale = min(target_width / orig_width, target_height / orig_height)
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)

            # Ресайз
            resized = cropped.resize((new_width, new_height), resample_filter)

            # Создаём фон и центрируем
            background = Image.new('RGB', (target_width, target_height), bg_color)
            x = (target_width - new_width) // 2
            y = (target_height - new_height) // 2

            # Вставка с маской, если есть альфа
            if has_alpha and resized.mode == 'RGBA':
                background.paste(resized, (x, y), resized)
            else:
                background.paste(resized, (x, y))

            # Сохраняем JPEG
            output_path.parent.mkdir(parents=True, exist_ok=True)
            background.save(output_path, 'JPEG', quality=quality)

            return f"УСПЕХ: {source_path.name} -> {output_path.name}", True

    except Exception as e:
        return f"ОШИБКА: {source_path.name} -> {str(e)}", False


def main():
    parser = argparse.ArgumentParser(
        description='Пакетная обработка PNG: обрезка прозрачных полей, масштабирование и сохранение в JPEG.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s -i ./input -o ./output -p SIZE_1024x1024
  %(prog)s -i ./images -r --size 800 600 -q 90 -w 8
        """
    )

    parser.add_argument('-p', '--preset', type=SizePreset.from_string,
                        default='SIZE_896x1200',
                        help='Предустановленный размер (по умолчанию SIZE_896x1200)')
    parser.add_argument('-s', '--size', nargs=2, type=int, metavar=('WIDTH', 'HEIGHT'),
                        help='Произвольный размер в пикселях (переопределяет --preset)')

    parser.add_argument('-i', '--input-dir', required=True,
                        help='Путь к директории с исходными файлами')
    parser.add_argument('-o', '--output-dir',
                        help='Выходная директория (по умолчанию совпадает с входной)')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Рекурсивно обрабатывать поддиректории')
    parser.add_argument('-q', '--quality', type=int, default=93, choices=range(1, 101),
                        metavar='[1-100]', help='Качество JPEG (по умолчанию 93)')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='Количество потоков (по умолчанию 4)')
    parser.add_argument('--resample', type=ResampleFilter.from_string, default='LANCZOS',
                        help='Алгоритм ресамплинга (NEAREST, BILINEAR, BICUBIC, LANCZOS, HAMMING, BOX). По умолчанию LANCZOS')
    parser.add_argument('--bg-color', type=parse_color, default='255,255,255',
                        help='Цвет фона в формате R,G,B (по умолчанию 255,255,255)')
    parser.add_argument('--no-overwrite', dest='overwrite', action='store_false',
                        help='Не перезаписывать существующие JPEG-файлы')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Подробный вывод (показывать результат каждого файла)')
    parser.set_defaults(overwrite=True)

    args = parser.parse_args()

    # Определяем целевой размер
    if args.size:
        target_width, target_height = args.size
    else:
        target_width, target_height = args.preset.width, args.preset.height

    # Проверка входной директории
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        logger.error(f"Ошибка: '{input_dir}' не является директорией или не существует.")
        sys.exit(1)

    # Выходная директория
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Поиск PNG-файлов
    png_files = find_png_files(input_dir, args.recursive)
    if not png_files:
        logger.warning(f"В директории '{input_dir}' не найдено PNG-файлов.")
        sys.exit(0)

    logger.info(f"Найдено файлов: {len(png_files)}")
    logger.info(f"Целевой размер: {target_width}x{target_height}")
    logger.info(f"Качество JPEG: {args.quality}%")
    logger.info(f"Алгоритм ресамплинга: {args.resample.name}")
    logger.info(f"Фон: {args.bg_color}")
    logger.info(f"Перезапись: {'да' if args.overwrite else 'нет'}")
    logger.info("-" * 40)

    success_count = 0
    error_count = 0

    # Подготовка аргументов для каждой задачи
    tasks = []
    for png_path in png_files:
        # Сохраняем относительный путь при рекурсивной обработке
        if args.recursive and args.output_dir:
            rel_path = png_path.relative_to(input_dir)
            out_path = output_dir / rel_path.with_suffix('.jpg')
        else:
            out_path = output_dir / png_path.with_suffix('.jpg').name
        tasks.append((png_path, out_path))

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(
                    process_single_image,
                    src,
                    dst,
                    target_width,
                    target_height,
                    args.quality,
                    args.resample.value,
                    args.bg_color,
                    args.overwrite
                ): (src, dst) for src, dst in tasks
            }

            # Прогресс-бар, если доступен tqdm
            if TQDM_AVAILABLE and not args.verbose:
                iterator = tqdm(as_completed(futures), total=len(futures), desc="Обработка", unit="file")
            else:
                iterator = as_completed(futures)

            for future in iterator:
                result_msg, is_success = future.result()
                if args.verbose:
                    logger.info(result_msg)
                if is_success:
                    success_count += 1
                elif "ОШИБКА" in result_msg:
                    error_count += 1
                # "ПРОПУЩЕН" не считается ошибкой, но и не успехом

    except KeyboardInterrupt:
        logger.warning("\nПрервано пользователем. Завершение работы...")
        sys.exit(1)

    logger.info("-" * 40)
    logger.info(f"Завершено. Успешно: {success_count}, Ошибок: {error_count}, "
                f"Пропущено: {len(png_files) - success_count - error_count}")


if __name__ == "__main__":
    main()