# utils/file_utils.py
import os
from typing import Optional, Dict, List
from aiogram.types import Message, Document, PhotoSize
from database.db_handler import DatabaseHandler

# Разрешенные типы файлов и максимальные размеры
ALLOWED_EXTENSIONS = {
    'pdf': 20 * 1024 * 1024,  # 20 MB
    'doc': 10 * 1024 * 1024,  # 10 MB
    'docx': 10 * 1024 * 1024,  # 10 MB
    'jpg': 5 * 1024 * 1024,  # 5 MB
    'jpeg': 5 * 1024 * 1024,  # 5 MB
    'png': 5 * 1024 * 1024,  # 5 MB
    'gif': 2 * 1024 * 1024,  # 2 MB
    'txt': 1 * 1024 * 1024,  # 1 MB
}

MAX_FILES_PER_OBJECT = 10  # Максимум файлов на объект

db = DatabaseHandler()


class FileProcessor:
    @staticmethod
    def get_file_extension(filename: str) -> str:
        """Получить расширение файла"""
        if not filename:
            return ""
        return filename.split('.')[-1].lower()

    @staticmethod
    def is_file_allowed(filename: str, file_size: int) -> tuple[bool, str]:
        """Проверить, разрешен ли файл"""
        extension = FileProcessor.get_file_extension(filename)

        if extension not in ALLOWED_EXTENSIONS:
            return False, f"❌ Файлы .{extension} не поддерживаются.\n\nРазрешены: {', '.join(ALLOWED_EXTENSIONS.keys())}"

        max_size = ALLOWED_EXTENSIONS[extension]
        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            return False, f"❌ Файл слишком большой! Максимум для .{extension}: {max_mb:.0f} МБ"

        return True, "OK"

    @staticmethod
    async def process_message_files(message: Message) -> List[Dict]:
        """Обработать все файлы из сообщения"""
        files_data = []

        # Обрабатываем документы
        if message.document:
            file_data = await FileProcessor.process_document(message.document, message.from_user.id)
            if file_data:
                files_data.append(file_data)

        # Обрабатываем фото
        if message.photo:
            file_data = await FileProcessor.process_photo(message.photo, message.from_user.id)
            if file_data:
                files_data.append(file_data)

        return files_data

    @staticmethod
    async def process_document(document: Document, user_id: int) -> Optional[Dict]:
        """Обработать документ"""
        filename = document.file_name or "document"
        file_size = document.file_size or 0

        is_allowed, error_msg = FileProcessor.is_file_allowed(filename, file_size)
        if not is_allowed:
            return None

        # Сохраняем информацию о файле в базу
        file_db_id = await db.save_file(
            file_id=document.file_id,
            file_unique_id=document.file_unique_id,
            file_name=filename,
            file_size=file_size,
            mime_type=document.mime_type or "application/octet-stream",
            file_type="document",
            uploaded_by=user_id
        )

        return {
            'db_id': file_db_id,
            'file_id': document.file_id,
            'file_name': filename,
            'file_size': file_size,
            'file_type': 'photo',
            'mime_type': 'image/jpeg'
        }

    @staticmethod
    async def attach_files_to_object(file_db_ids: List[int], object_type: str, object_id: int):
        """Привязать файлы к объекту"""
        for file_db_id in file_db_ids:
            await db.attach_file_to_object(file_db_id, object_type, object_id)

    @staticmethod
    def format_file_list(files: List[Dict]) -> str:
        """Форматировать список файлов для отображения"""
        if not files:
            return "📁 Файлов нет"

        text = f"📁 Файлы ({len(files)}):\n"
        for i, file_info in enumerate(files, 1):
            file_type_emoji = {
                'document': '📄',
                'photo': '🖼',
                'video': '🎥'
            }.get(file_info['file_type'], '📎')

            size_mb = (file_info['file_size'] or 0) / (1024 * 1024)
            uploader = f"{file_info.get('first_name', 'Неизвестно')} {file_info.get('last_name', '')}"

            text += f"{i}. {file_type_emoji} {file_info['file_name']}"
            if size_mb > 0:
                text += f" ({size_mb:.1f} МБ)"
            text += f"\n   👤 {uploader}\n"

        return text

    @staticmethod
    def get_file_type_emoji(file_type: str) -> str:
        """Получить эмодзи для типа файла"""
        return {
            'document': '📄',
            'photo': '🖼',
            'video': '🎥'
        }.get(file_type, '📎')

    @staticmethod
    async def process_photo(photo_sizes: List[PhotoSize], user_id: int) -> Optional[Dict]:
        """Обработать фото (берем самое большое)"""
        if not photo_sizes:
            return None

        # Берем фото наибольшего размера
        largest_photo = max(photo_sizes, key=lambda x: x.file_size or 0)

        filename = f"photo_{largest_photo.file_unique_id}.jpg"
        file_size = largest_photo.file_size or 0

        is_allowed, error_msg = FileProcessor.is_file_allowed(filename, file_size)
        if not is_allowed:
            return None

        # Сохраняем информацию о файле в базу
        file_db_id = await db.save_file(
            file_id=largest_photo.file_id,
            file_unique_id=largest_photo.file_unique_id,
            file_name=filename,
            file_size=file_size,
            mime_type="image/jpeg",
            file_type="photo",
            uploaded_by=user_id
        )

        return {
            'db_id': file_db_id,
            'file_id': largest_photo.file_id,
            'file_name': filename,
            'file_size': file_size,
            'file_type': 'document',
            'mime_type': 'image/jpeg'

    }