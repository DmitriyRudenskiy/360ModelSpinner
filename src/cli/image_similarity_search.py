#!/usr/bin/env python3
"""
Консольный скрипт для поиска схожести изображений по эмбедингам и составления списка уникальных изображений.
Использует модель CLIP для получения эмбедингов и вычисления косинусной схожести.

Возможности:
- Поиск схожих изображений по тексту и изображению
- Составление списка уникальных изображений с настраиваемым порогом схожести
- Группировка изображений по схожести
- Сохранение результатов в JSON файл

Автор: MiniMax Agent
"""

import os
import argparse
import json
import pickle
import hashlib
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import numpy as np
from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel
from sklearn.metrics.pairwise import cosine_similarity
import warnings

warnings.filterwarnings('ignore')


class ImageEmbeddingSearcher:
    """Класс для поиска схожести изображений по эмбедингам."""
    
    def __init__(self, model_name: str = "openai/clip-vit-large-patch14-336"):
        """
        Инициализация поисковика.
        
        Args:
            model_name: Название модели CLIP или путь к локальной модели
        """
        print(f"Загрузка модели {model_name}...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Определяем, является ли model_name локальным путем
        model_path = Path(model_name)
        if model_path.exists() and model_path.is_dir():
            # Локальная модель
            print(f"📁 Загрузка локальной модели из: {model_path}")
            self.model = CLIPModel.from_pretrained(str(model_path))
            self.processor = CLIPProcessor.from_pretrained(str(model_path), use_fast=True)
        else:
            # Hugging Face Hub модель
            print(f"🌐 Скачивание модели из Hugging Face Hub: {model_name}")
            try:
                self.model = CLIPModel.from_pretrained(model_name)
                self.processor = CLIPProcessor.from_pretrained(model_name, use_fast=True)
            except Exception as e:
                print(f"❌ Ошибка при загрузке модели из Hugging Face: {e}")
                print(f"💡 Возможно, модель не найдена. Попробуйте:")
                print(f"   python download_model.py --model {model_name}")
                raise
        
        self.model.to(self.device)
        self.model.eval()
        
        self.embeddings = {}
        self.image_paths = {}
        self.cache_dir = Path(".image_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        print(f"✅ Модель загружена на устройство: {self.device}")
    
    def _get_cache_key(self, image_path: str) -> str:
        """Генерация ключа кеша на основе пути к изображению."""
        return hashlib.md5(image_path.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Получение пути к файлу кеша."""
        return self.cache_dir / f"{cache_key}.pkl"
    
    def load_image_embeddings(self, image_dir: str, cache: bool = True) -> int:
        """
        Загрузка эмбедингов изображений из директории.
        
        Args:
            image_dir: Путь к директории с изображениями
            cache: Использовать ли кеширование
            
        Returns:
            Количество загруженных изображений
        """
        image_dir = Path(image_dir)
        if not image_dir.exists():
            raise FileNotFoundError(f"Директория {image_dir} не найдена")
        
        # Поддерживаемые форматы изображений
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        
        image_files = []
        for ext in supported_formats:
            image_files.extend(image_dir.rglob(f"*{ext}"))
            image_files.extend(image_dir.rglob(f"*{ext.upper()}"))
        
        if not image_files:
            raise ValueError(f"В директории {image_dir} не найдено изображений")
        
        print(f"Найдено {len(image_files)} изображений в {image_dir}")
        
        loaded_count = 0
        for img_path in image_files:
            try:
                cache_key = self._get_cache_key(str(img_path))
                cache_path = self._get_cache_path(cache_key)
                
                # Проверяем кеш
                if cache and cache_path.exists():
                    try:
                        with open(cache_path, 'rb') as f:
                            embedding = pickle.load(f)
                        self.embeddings[str(img_path)] = embedding
                        self.image_paths[str(img_path)] = str(img_path)
                        loaded_count += 1
                        continue
                    except Exception as e:
                        print(f"Ошибка при загрузке кеша для {img_path}: {e}")
                
                # Вычисляем эмбединг
                embedding = self._compute_embedding(str(img_path))
                
                # Сохраняем в кеш
                if cache:
                    try:
                        with open(cache_path, 'wb') as f:
                            pickle.dump(embedding, f)
                    except Exception as e:
                        print(f"Ошибка при сохранении кеша для {img_path}: {e}")
                
                self.embeddings[str(img_path)] = embedding
                self.image_paths[str(img_path)] = str(img_path)
                loaded_count += 1
                
                if loaded_count % 50 == 0:
                    print(f"Обработано {loaded_count} изображений...")
                    
            except Exception as e:
                print(f"Ошибка при обработке {img_path}: {e}")
                continue
        
        print(f"Загружено {loaded_count} эмбедингов изображений")
        return loaded_count
    
    def _compute_embedding(self, image_path: str) -> np.ndarray:
        """Вычисление эмбединга для одного изображения."""
        try:
            image = Image.open(image_path).convert('RGB')
            
            with torch.no_grad():
                inputs = self.processor(images=image, return_tensors="pt")
                image_features = self.model.get_image_features(**inputs)
                # Нормализуем эмбединг
                embedding = image_features / image_features.norm(dim=-1, keepdim=True)
                embedding = embedding.cpu().numpy().flatten()
            
            return embedding
            
        except Exception as e:
            raise ValueError(f"Ошибка при вычислении эмбединга для {image_path}: {e}")
    
    def compute_text_embedding(self, text: str) -> np.ndarray:
        """
        Вычисление эмбединга для текстового запроса.
        
        Args:
            text: Текстовый запрос
            
        Returns:
            Эмбединг текста
        """
        with torch.no_grad():
            inputs = self.processor(text=text, return_tensors="pt", padding=True)
            text_features = self.model.get_text_features(**inputs)
            # Нормализуем эмбединг
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            text_features = text_features.cpu().numpy()
        
        return text_features.flatten()
    
    def find_similar_images(self, 
                          query_embedding: np.ndarray, 
                          top_k: int = 10,
                          min_similarity: float = 0.0) -> List[Tuple[str, float]]:
        """
        Поиск похожих изображений.
        
        Args:
            query_embedding: Эмбединг запроса
            top_k: Количество результатов
            min_similarity: Минимальная схожесть
            
        Returns:
            Список кортежей (путь к изображению, схожесть), отсортированный по убыванию схожести
        """
        if not self.embeddings:
            raise ValueError("Эмбединги не загружены. Сначала вызовите load_image_embeddings()")
        
        # Подготавливаем матрицу эмбедингов
        embeddings_matrix = np.array(list(self.embeddings.values()))
        
        # Вычисляем косинусную схожесть
        similarities = cosine_similarity([query_embedding], embeddings_matrix)[0]
        
        # Создаем список результатов
        results = []
        for i, similarity in enumerate(similarities):
            if similarity >= min_similarity:
                image_path = list(self.image_paths.keys())[i]
                results.append((image_path, float(similarity)))
        
        # Сортируем по убыванию схожести и берем top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def search_by_text(self, query: str, top_k: int = 10, min_similarity: float = 0.0) -> List[Tuple[str, float]]:
        """
        Поиск изображений по текстовому запросу.
        
        Args:
            query: Текстовый запрос
            top_k: Количество результатов
            min_similarity: Минимальная схожесть
            
        Returns:
            Список кортежей (путь к изображению, схожесть)
        """
        print(f"Поиск по запросу: '{query}'")
        query_embedding = self.compute_text_embedding(query)
        return self.find_similar_images(query_embedding, top_k, min_similarity)
    
    def search_by_image(self, query_image_path: str, top_k: int = 10, min_similarity: float = 0.0) -> List[Tuple[str, float]]:
        """
        Поиск изображений, похожих на заданное изображение.
        
        Args:
            query_image_path: Путь к изображению-запросу
            top_k: Количество результатов
            min_similarity: Минимальная схожесть
            
        Returns:
            Список кортежей (путь к изображению, схожесть)
        """
        if not os.path.exists(query_image_path):
            raise FileNotFoundError(f"Изображение {query_image_path} не найдено")
        
        print(f"Поиск похожих изображений для: {query_image_path}")
        
        # Вычисляем эмбединг изображения-запроса
        query_embedding = self._compute_embedding(query_image_path)
        return self.find_similar_images(query_embedding, top_k, min_similarity)
    
    def print_results(self, results: List[Tuple[str, float]], title: str = "Результаты поиска"):
        """Вывод результатов в консоль."""
        print(f"\n{title}")
        print("=" * 80)
        
        if not results:
            print("Результаты не найдены")
            return
        
        for i, (image_path, similarity) in enumerate(results, 1):
            relative_path = Path(image_path).name
            print(f"{i:2d}. {relative_path}")
            print(f"    Схожесть: {similarity:.4f}")
            print(f"    Полный путь: {image_path}")
            print()
    
    def get_statistics(self) -> Dict:
        """Получение статистики по загруженным изображениям."""
        if not self.embeddings:
            return {"total_images": 0}
        
        embeddings_array = np.array(list(self.embeddings.values()))
        return {
            "total_images": len(self.embeddings),
            "embedding_dim": embeddings_array.shape[1],
            "min_similarity_range": float(np.min(embeddings_array)),
            "max_similarity_range": float(np.max(embeddings_array)),
            "cache_enabled": True
        }
    
    def group_images_by_similarity(self, threshold: float, show_details: bool = False) -> Tuple[List[List[str]], Dict[Tuple[str, str], float]]:
        """
        Группировка изображений по схожести.
        
        Args:
            threshold: Пороговое значение схожести (0.0 - 1.0)
            show_details: Показывать ли детали о парах похожих изображений
            
        Returns:
            Кортеж (список групп, словарь пар похожих изображений)
        """
        if not self.embeddings:
            raise ValueError("Эмбединги не загружены. Сначала вызовите load_image_embeddings()")
        
        print(f"🔍 Группировка изображений по схожести (порог: {threshold:.4f})...")
        
        image_paths = list(self.image_paths.keys())
        embeddings_matrix = np.array(list(self.embeddings.values()))
        
        # Вычисляем матрицу схожести
        similarity_matrix = cosine_similarity(embeddings_matrix)
        
        # Словарь для хранения всех пар похожих изображений
        similar_pairs = {}
        
        # Инициализация групп
        groups = []
        assigned = set()
        
        # Для каждого изображения ищем похожие
        for i, image_path in enumerate(image_paths):
            if image_path in assigned:
                continue
            
            # Начинаем новую группу с текущего изображения
            group = [image_path]
            assigned.add(image_path)
            
            # Ищем похожие изображения
            for j, other_path in enumerate(image_paths):
                if other_path in assigned or i == j:
                    continue
                
                similarity = similarity_matrix[i][j]
                if similarity >= threshold:
                    group.append(other_path)
                    assigned.add(other_path)
                    
                    # Сохраняем пару похожих изображений
                    pair_key = tuple(sorted([image_path, other_path]))
                    similar_pairs[pair_key] = similarity
            
            groups.append(group)
        
        print(f"✅ Найдено {len(groups)} групп схожих изображений")
        print(f"📊 Обнаружено {len(similar_pairs)} пар похожих изображений")
        
        return groups, similar_pairs
    
    def _get_image_area(self, image_path: str) -> int:
        """
        Вычисляет площадь изображения (ширина * высота в пикселях).
        
        Args:
            image_path: Путь к изображению
            
        Returns:
            Площадь изображения в пикселях, или 0 если изображение не найдено или повреждено
        """
        try:
            if not Path(image_path).exists():
                return 0
            
            with Image.open(image_path) as img:
                width, height = img.size
                return width * height
        except Exception:
            return 0
    
    def find_unique_images(self, threshold: float = 0.8, show_details: bool = False) -> Tuple[List[str], Dict[Tuple[str, str], float]]:
        """
        Поиск уникальных изображений (представителей каждой группы).
        
        Args:
            threshold: Пороговое значение схожести
            show_details: Показывать ли детали о парах похожих изображений
            
        Returns:
            Кортеж (список путей к уникальным изображениям, словарь пар похожих изображений)
        """
        groups, similar_pairs = self.group_images_by_similarity(threshold, show_details)
        
        # Берем первое изображение из каждой группы как представителя
        unique_images = []
        for group in groups:
            # Сортируем группу по площади изображения (большая площадь = больше деталей)
            group_sorted = sorted(group, key=lambda x: self._get_image_area(x), reverse=True)
            unique_images.append(group_sorted[0])
        
        return unique_images, similar_pairs
    
    def print_similarity_pairs(self, similar_pairs: Dict[Tuple[str, str], float], threshold: float, max_pairs: int = 50):
        """
        Вывод детальной информации о парах похожих изображений.
        
        Args:
            similar_pairs: Словарь пар похожих изображений
            threshold: Использованное пороговое значение
            max_pairs: Максимальное количество пар для вывода
        """
        if not similar_pairs:
            print(f"\n🔍 Детали схожести (порог: {threshold:.4f})")
            print("=" * 80)
            print("Пары похожих изображений не найдены")
            return
        
        print(f"\n🔍 Детали схожести (порог: {threshold:.4f})")
        print("=" * 80)
        print(f"📊 Найдено {len(similar_pairs)} пар похожих изображений")
        print()
        
        # Сортируем пары по убыванию схожести
        sorted_pairs = sorted(similar_pairs.items(), key=lambda x: x[1], reverse=True)
        
        # Ограничиваем количество выводимых пар
        pairs_to_show = sorted_pairs[:max_pairs]
        
        for i, ((img1, img2), similarity) in enumerate(pairs_to_show, 1):
            name1 = Path(img1).name
            name2 = Path(img2).name
            
            print(f"{i:2d}. {name1} ↔ {name2}")
            print(f"    Схожесть: {similarity:.4f}")
            print(f"    Путь 1: {img1}")
            print(f"    Путь 2: {img2}")
            print()
        
        if len(sorted_pairs) > max_pairs:
            print(f"... и еще {len(sorted_pairs) - max_pairs} пар")
            print(f"Для просмотра всех пар используйте большее значение max_pairs")
    
    def print_unique_images(self, unique_images: List[str], threshold: float, title: str = "Список уникальных изображений", similar_pairs: Dict[Tuple[str, str], float] = None, show_details: bool = False):
        """
        Вывод списка уникальных изображений.
        
        Args:
            unique_images: Список путей к уникальным изображениям
            threshold: Использованное пороговое значение
            title: Заголовок для вывода
            similar_pairs: Словарь пар похожих изображений
            show_details: Показывать ли детали о парах похожих изображений
        """
        print(f"\n{title} (порог: {threshold:.4f})")
        print("=" * 80)
        
        if not unique_images:
            print("Уникальные изображения не найдены")
            return
        
        total_images = len(self.embeddings)
        unique_count = len(unique_images)
        duplicates_removed = total_images - unique_count
        
        print(f"📊 Статистика:")
        print(f"   • Всего изображений: {total_images}")
        print(f"   • Уникальных изображений: {unique_count}")
        print(f"   • Удалено похожих: {duplicates_removed}")
        print(f"   • Сжатие: {(duplicates_removed/total_images)*100:.1f}%")
        
        if similar_pairs:
            print(f"   • Пар похожих изображений: {len(similar_pairs)}")
        print()
        
        for i, image_path in enumerate(unique_images, 1):
            file_size = Path(image_path).stat().st_size if Path(image_path).exists() else 0
            size_mb = file_size / (1024 * 1024)
            area = self._get_image_area(image_path)
            
            # Форматируем площадь для читаемого вывода
            if area >= 1_000_000:
                area_str = f"{area/1_000_000:.1f} МП"
            elif area >= 1000:
                area_str = f"{area/1000:.0f} КП"
            else:
                area_str = f"{area} П"
            
            print(f"{i:2d}. {Path(image_path).name}")
            print(f"    Путь: {image_path}")
            print(f"    Площадь: {area_str} ({area:,} пикселей)")
            print(f"    Размер файла: {size_mb:.2f} MB")
            print()
    
    def save_unique_images_list(self, unique_images: List[str], output_file: str, threshold: float) -> bool:
        """
        Сохранение списка уникальных изображений в файл.
        
        Args:
            unique_images: Список путей к уникальным изображениям
            output_file: Путь к выходному файлу
            threshold: Использованное пороговое значение
            
        Returns:
            True если успешно, False иначе
        """
        try:
            output_data = {
                "threshold": threshold,
                "total_images": len(self.embeddings),
                "unique_images": unique_images,
                "unique_count": len(unique_images),
                "duplicates_removed": len(self.embeddings) - len(unique_images),
                "compression_ratio": (len(self.embeddings) - len(unique_images)) / len(self.embeddings) if len(self.embeddings) > 0 else 0,
                "generated_at": "2025-12-17 15:40:06"
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Список уникальных изображений сохранен в: {output_file}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при сохранении файла: {e}")
            return False
    
    def copy_unique_images(self, unique_images: List[str], output_dir: str, preserve_structure: bool = True) -> bool:
        """
        Копирование уникальных изображений в отдельную директорию.
        
        Args:
            unique_images: Список путей к уникальным изображениям
            output_dir: Директория для копирования
            preserve_structure: Сохранять ли структуру поддиректорий
            
        Returns:
            True если успешно, False иначе
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            print(f"📁 Копирование {len(unique_images)} уникальных изображений в: {output_path}")
            
            copied_count = 0
            failed_count = 0
            
            for i, source_path in enumerate(unique_images, 1):
                try:
                    source_file = Path(source_path)
                    
                    if not source_file.exists():
                        print(f"   ⚠️  Файл не найден: {source_path}")
                        failed_count += 1
                        continue
                    
                    # Определяем путь назначения
                    if preserve_structure:
                        # Сохраняем относительную структуру
                        try:
                            # Если это относительный путь, используем его как есть
                            if not source_file.is_absolute():
                                relative_path = source_file
                            else:
                                # Если это абсолютный путь, вычисляем относительный от рабочей директории
                                relative_path = source_file.relative_to(Path.cwd())
                            dest_path = output_path / relative_path
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                        except ValueError:
                            # Если не удалось вычислить относительный путь, просто копируем в корень
                            dest_path = output_path / source_file.name
                    else:
                        # Просто копируем в корневую директорию
                        dest_path = output_path / source_file.name
                    
                    # Копируем файл
                    shutil.copy2(source_file, dest_path)
                    copied_count += 1
                    
                    if i % 10 == 0 or i == len(unique_images):
                        print(f"   📋 Обработано: {i}/{len(unique_images)} файлов")
                    
                except Exception as e:
                    print(f"   ❌ Ошибка копирования {source_path}: {e}")
                    failed_count += 1
            
            print(f"\n✅ Копирование завершено:")
            print(f"   • Успешно скопировано: {copied_count}")
            print(f"   • Ошибок: {failed_count}")
            print(f"   • Директория: {output_path}")
            
            return copied_count > 0
            
        except Exception as e:
            print(f"❌ Ошибка при копировании изображений: {e}")
            return False


def main():
    """Главная функция с интерфейсом командной строки."""
    parser = argparse.ArgumentParser(
        description="Поиск схожести изображений по эмбедингам",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Поиск уникальных изображений
  python image_similarity_search.py --images ./photos --find-unique --similarity-threshold 0.8

  # Поиск уникальных изображений с сохранением в файл
  python image_similarity_search.py --images ./photos --find-unique --similarity-threshold 0.7 --output-file unique_images.json

  # Загрузка изображений и поиск по тексту
  python image_similarity_search.py --images ./photos --search-text "кот" --top-k 5

  # Поиск по изображению
  python image_similarity_search.py --images ./photos --search-image query.jpg --top-k 10

  # Интерактивный режим
  python image_similarity_search.py --images ./photos --interactive

  # Статистика
  python image_similarity_search.py --images ./photos --stats
        """
    )
    
    # Основные аргументы
    parser.add_argument("--images", "-i", 
                       help="Путь к директории с изображениями",
                       required=True)
    
    # Режимы поиска
    search_group = parser.add_mutually_exclusive_group()
    search_group.add_argument("--search-text", "-t",
                             help="Поиск по текстовому запросу")
    search_group.add_argument("--search-image", "-s",
                             help="Поиск похожих изображений для заданного")
    search_group.add_argument("--find-unique", "-u",
                             action="store_true",
                             help="Составить список уникальных изображений")
    search_group.add_argument("--interactive", "-r",
                             action="store_true",
                             help="Интерактивный режим")
    search_group.add_argument("--stats",
                             action="store_true",
                             help="Показать статистику")
    
    # Параметры поиска
    parser.add_argument("--top-k", "-k",
                       type=int, default=10,
                       help="Количество результатов (по умолчанию: 10)")
    parser.add_argument("--min-similarity", "-m",
                       type=float, default=0.0,
                       help="Минимальная схожесть (по умолчанию: 0.0)")
    parser.add_argument("--similarity-threshold", "-th",
                       type=float, default=0.95,
                       help="Порог схожести для группировки изображений (0.0-1.0, по умолчанию: 0.95)")
    parser.add_argument("--show-similarity-details", "-d",
                       action="store_true",
                       help="Показать детали о парах похожих изображений")
    parser.add_argument("--max-similarity-pairs", "-mp",
                       type=int, default=50,
                       help="Максимальное количество пар для вывода (по умолчанию: 50)")
    parser.add_argument("--output-file", "-o",
                       help="Файл для сохранения списка уникальных изображений (JSON)")
    parser.add_argument("--copy-unique-to", "-c",
                       help="Директория для копирования уникальных изображений")
    parser.add_argument("--no-cache",
                       action="store_true",
                       help="Отключить кеширование")
    
    # Параметры модели
    parser.add_argument("--model",
                       default="openai/clip-vit-large-patch14-336",
                       help="Название модели CLIP или путь к локальной модели (по умолчанию: openai/clip-vit-large-patch14-336)")
    
    args = parser.parse_args()
    
    try:
        # Инициализация поисковика
        searcher = ImageEmbeddingSearcher(args.model)
        
        # Загрузка изображений
        print("Загрузка изображений...")
        loaded_count = searcher.load_image_embeddings(args.images, cache=not args.no_cache)
        
        if loaded_count == 0:
            print("Не удалось загрузить изображения")
            return
        
        # Выполнение поиска
        if args.stats:
            stats = searcher.get_statistics()
            print("\nСтатистика:")
            print("=" * 40)
            for key, value in stats.items():
                print(f"{key}: {value}")
        
        elif args.find_unique:
            print(f"\n🎯 Поиск уникальных изображений с порогом схожести: {args.similarity_threshold}")
            unique_images, similar_pairs = searcher.find_unique_images(args.similarity_threshold, args.show_similarity_details)
            searcher.print_unique_images(unique_images, args.similarity_threshold, "Список уникальных изображений", similar_pairs, args.show_similarity_details)
            
            # Показываем детали о парах похожих изображений если запрошено
            if args.show_similarity_details:
                searcher.print_similarity_pairs(similar_pairs, args.similarity_threshold, args.max_similarity_pairs)
            
            # Сохраняем в файл если указан
            if args.output_file:
                searcher.save_unique_images_list(unique_images, args.output_file, args.similarity_threshold)
            
            # Копируем уникальные изображения если указана директория
            if args.copy_unique_to:
                searcher.copy_unique_images(unique_images, args.copy_unique_to)
        
        elif args.search_text:
            results = searcher.search_by_text(args.search_text, args.top_k, args.min_similarity)
            searcher.print_results(results, f"Результаты поиска по запросу: '{args.search_text}'")
        
        elif args.search_image:
            results = searcher.search_by_image(args.search_image, args.top_k, args.min_similarity)
            searcher.print_results(results, f"Результаты поиска для изображения: {args.search_image}")
        
        elif args.interactive:
            print("\nИнтерактивный режим. Введите команды:")
            print("- 'text <запрос>' для поиска по тексту")
            print("- 'image <путь>' для поиска по изображению")
            print("- 'unique <порог>' для поиска уникальных изображений")
            print("- 'copy <директория>' для копирования последних найденных уникальных изображений")
            print("- 'stats' для показа статистики")
            print("- 'quit' для выхода")
            
            # Переменная для хранения последних найденных уникальных изображений
            last_unique_images = None
            
            while True:
                try:
                    command = input("\n> ").strip()
                    
                    if command.lower() == 'quit':
                        break
                    
                    elif command.lower() == 'stats':
                        stats = searcher.get_statistics()
                        print("\nСтатистика:")
                        print("=" * 40)
                        for key, value in stats.items():
                            print(f"{key}: {value}")
                    
                    elif command.lower().startswith('text '):
                        query = command[5:].strip()
                        if query:
                            results = searcher.search_by_text(query, args.top_k, args.min_similarity)
                            searcher.print_results(results, f"Результаты поиска по запросу: '{query}'")
                        else:
                            print("Укажите текстовый запрос")
                    
                    elif command.lower().startswith('image '):
                        image_path = command[6:].strip()
                        if image_path:
                            try:
                                results = searcher.search_by_image(image_path, args.top_k, args.min_similarity)
                                searcher.print_results(results, f"Результаты поиска для изображения: {image_path}")
                            except Exception as e:
                                print(f"Ошибка: {e}")
                        else:
                            print("Укажите путь к изображению")
                    
                    elif command.lower().startswith('unique '):
                        threshold_str = command[7:].strip()
                        try:
                            threshold = float(threshold_str) if threshold_str else args.similarity_threshold
                            if not (0.0 <= threshold <= 1.0):
                                print("Порог должен быть в диапазоне 0.0 - 1.0")
                            else:
                                unique_images, similar_pairs = searcher.find_unique_images(threshold, args.show_similarity_details)
                                searcher.print_unique_images(unique_images, threshold, f"Список уникальных изображений (порог: {threshold})", similar_pairs, args.show_similarity_details)
                                
                                # Сохраняем последние найденные уникальные изображения
                                last_unique_images = unique_images
                                
                                # Показываем детали если запрошено
                                if args.show_similarity_details:
                                    searcher.print_similarity_pairs(similar_pairs, threshold, args.max_similarity_pairs)
                        except ValueError:
                            print("Укажите корректное числовое значение порога")
                    
                    elif command.lower().startswith('copy '):
                        copy_dir = command[5:].strip()
                        if copy_dir:
                            if last_unique_images:
                                try:
                                    searcher.copy_unique_images(last_unique_images, copy_dir)
                                    print(f"✅ Уникальные изображения скопированы в директорию: {copy_dir}")
                                except Exception as e:
                                    print(f"❌ Ошибка при копировании: {e}")
                            else:
                                print("❌ Сначала выполните команду 'unique' для поиска уникальных изображений")
                        else:
                            print("Укажите директорию для копирования")
                    
                    else:
                        print("Неизвестная команда. Доступные команды: text, image, unique, copy, stats, quit")
                
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    main()