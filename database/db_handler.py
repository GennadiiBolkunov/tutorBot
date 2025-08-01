# database/db_handler.py
import aiosqlite
import os
from datetime import datetime
from typing import Optional, List, Dict


class DatabaseHandler:
    def __init__(self, db_path: str = "tutor_bot.db"):
        self.db_path = db_path

    async def init_db(self):
        """Инициализация базы данных с созданием таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица заявок на регистрацию
            await db.execute("""
                CREATE TABLE IF NOT EXISTS registration_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    grade INTEGER,
                    parent_contact TEXT,
                    motivation TEXT,
                    request_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',  -- pending, approved, rejected
                    admin_comment TEXT
                )
            """)

            # Таблица зарегистрированных пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    phone TEXT,
                    grade INTEGER,
                    parent_contact TEXT,
                    registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    notes TEXT
                )
            """)

            # Таблица администраторов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_super_admin BOOLEAN DEFAULT FALSE
                )
            """)

            # Таблица заданий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    grade_level INTEGER,
                    difficulty TEXT DEFAULT 'medium',  -- easy, medium, hard
                    created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    due_date DATETIME,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES admins (telegram_id)
                )
            """)

            # Таблица результатов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    assignment_id INTEGER,
                    score INTEGER,
                    max_score INTEGER,
                    completed_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    comment TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    FOREIGN KEY (assignment_id) REFERENCES assignments (id)
                )
            """)

            await db.commit()

    # === МЕТОДЫ ДЛЯ ЗАЯВОК НА РЕГИСТРАЦИЮ ===

    async def create_registration_request(self, telegram_id: int, username: str,
                                          first_name: str, last_name: str,
                                          phone: str, grade: int, parent_contact: str,
                                          motivation: str) -> bool:
        """Создать заявку на регистрацию"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO registration_requests 
                    (telegram_id, username, first_name, last_name, phone, grade, parent_contact, motivation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (telegram_id, username, first_name, last_name, phone, grade, parent_contact, motivation))
                await db.commit()
                return True
        except aiosqlite.IntegrityError:
            return False  # Заявка уже существует

    async def get_pending_requests(self) -> List[Dict]:
        """Получить все ожидающие заявки"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM registration_requests 
                WHERE status = 'pending' 
                ORDER BY request_date ASC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def approve_registration(self, request_id: int, admin_comment: str = "") -> bool:
        """Одобрить заявку и создать пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем данные заявки
            cursor = await db.execute("""
                SELECT * FROM registration_requests WHERE id = ? AND status = 'pending'
            """, (request_id,))
            request_data = await cursor.fetchone()

            if not request_data:
                return False

            try:
                # Создаем пользователя
                await db.execute("""
                    INSERT INTO users (telegram_id, username, first_name, last_name, phone, grade, parent_contact)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (request_data[1], request_data[2], request_data[3], request_data[4],
                      request_data[5], request_data[6], request_data[7]))

                # Обновляем статус заявки
                await db.execute("""
                    UPDATE registration_requests 
                    SET status = 'approved', admin_comment = ?
                    WHERE id = ?
                """, (admin_comment, request_id))

                await db.commit()
                return True
            except Exception:
                return False

    async def reject_registration(self, request_id: int, admin_comment: str) -> bool:
        """Отклонить заявку"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE registration_requests 
                SET status = 'rejected', admin_comment = ?
                WHERE id = ? AND status = 'pending'
            """, (admin_comment, request_id))
            await db.commit()
            return True

    # === МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===

    async def is_user_registered(self, telegram_id: int) -> bool:
        """Проверить, зарегистрирован ли пользователь"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 1 FROM users WHERE telegram_id = ? AND is_active = TRUE
            """, (telegram_id,))
            return await cursor.fetchone() is not None

    async def has_pending_request(self, telegram_id: int) -> bool:
        """Проверить, есть ли ожидающая заявка"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 1 FROM registration_requests 
                WHERE telegram_id = ? AND status = 'pending'
            """, (telegram_id,))
            return await cursor.fetchone() is not None

    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить данные пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM users WHERE telegram_id = ?
            """, (telegram_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    # === МЕТОДЫ ДЛЯ АДМИНИСТРАТОРОВ ===

    async def is_admin(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 1 FROM admins WHERE telegram_id = ?
            """, (telegram_id,))
            return await cursor.fetchone() is not None

    async def add_admin(self, telegram_id: int, username: str, first_name: str, is_super_admin: bool = False):
        """Добавить администратора"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO admins (telegram_id, username, first_name, is_super_admin)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, username, first_name, is_super_admin))
            await db.commit()

    async def get_all_users(self) -> List[Dict]:
        """Получить всех зарегистрированных пользователей"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM users WHERE is_active = TRUE ORDER BY registration_date DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]