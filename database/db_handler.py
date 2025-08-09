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
                    solution_text TEXT,
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

    # === МЕТОДЫ ДЛЯ ЗАДАНИЙ ===

    async def create_assignment(self, title: str, description: str, grade_level: int,
                                difficulty: str, created_by: int, due_date: str = None) -> int:
        """Создать новое задание"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO assignments (title, description, grade_level, difficulty, created_by, due_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, description, grade_level, difficulty, created_by, due_date))
            await db.commit()
            return cursor.lastrowid

    async def get_assignments_for_grade(self, grade: int, is_active: bool = True) -> List[Dict]:
        """Получить задания для определенного класса"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM assignments 
                WHERE (grade_level = ? OR grade_level = 0) AND is_active = ?
                ORDER BY created_date DESC
            """, (grade, is_active))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_assignment_by_id(self, assignment_id: int) -> Optional[Dict]:
        """Получить задание по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM assignments WHERE id = ?
            """, (assignment_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_assignments(self) -> List[Dict]:
        """Получить все задания (для админа)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT a.*, u.first_name as creator_name 
                FROM assignments a
                LEFT JOIN admins u ON a.created_by = u.telegram_id
                ORDER BY a.created_date DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def deactivate_assignment(self, assignment_id: int) -> bool:
        """Деактивировать задание"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE assignments SET is_active = FALSE WHERE id = ?
            """, (assignment_id,))
            await db.commit()
            return cursor.rowcount > 0

    # === МЕТОДЫ ДЛЯ РЕЗУЛЬТАТОВ ===

    async def submit_solution(self, user_id: int, assignment_id: int, solution_text: str) -> int:
        """Отправить решение задания"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем, не отправлял ли уже решение
            cursor = await db.execute("""
                SELECT id FROM results WHERE user_id = ? AND assignment_id = ?
            """, (user_id, assignment_id))
            existing = await cursor.fetchone()

            if existing:
                # Обновляем существующее решение
                await db.execute("""
                    UPDATE results SET solution_text = ?, completed_date = CURRENT_TIMESTAMP, score = NULL
                    WHERE user_id = ? AND assignment_id = ?
                """, (solution_text, user_id, assignment_id))
                result_id = existing[0]
            else:
                # Создаем новое решение
                cursor = await db.execute("""
                    INSERT INTO results (user_id, assignment_id, solution_text)
                    VALUES (?, ?, ?)
                """, (user_id, assignment_id, solution_text))
                result_id = cursor.lastrowid

            await db.commit()
            return result_id

    async def get_user_solutions(self, user_id: int) -> List[Dict]:
        """Получить все решения пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.*, a.title, a.description, a.difficulty
                FROM results r
                JOIN assignments a ON r.assignment_id = a.id
                WHERE r.user_id = ?
                ORDER BY r.completed_date DESC
            """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_ungraded_solutions(self) -> List[Dict]:
        """Получить непроверенные решения"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.*, a.title, a.grade_level, u.first_name, u.last_name
                FROM results r
                JOIN assignments a ON r.assignment_id = a.id
                JOIN users u ON r.user_id = u.telegram_id
                WHERE r.score IS NULL
                ORDER BY r.completed_date ASC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def grade_solution(self, result_id: int, score: int, max_score: int, comment: str = "") -> bool:
        """Оценить решение"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE results 
                SET score = ?, max_score = ?, comment = ?
                WHERE id = ?
            """, (score, max_score, comment, result_id))
            await db.commit()
            return cursor.rowcount > 0

    async def get_user_stats(self, user_id: int) -> Dict:
        """Получить статистику пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            # Общая статистика
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total_assignments,
                    COUNT(CASE WHEN score IS NOT NULL THEN 1 END) as graded_assignments,
                    AVG(CASE WHEN score IS NOT NULL AND max_score > 0 THEN (score * 100.0 / max_score) END) as avg_percentage
                FROM results 
                WHERE user_id = ?
            """, (user_id,))
            stats = await cursor.fetchone()

            # Статистика по сложности
            cursor = await db.execute("""
                SELECT 
                    a.difficulty,
                    COUNT(*) as count,
                    AVG(CASE WHEN r.score IS NOT NULL AND r.max_score > 0 THEN (r.score * 100.0 / r.max_score) END) as avg_percentage
                FROM results r
                JOIN assignments a ON r.assignment_id = a.id
                WHERE r.user_id = ? AND r.score IS NOT NULL
                GROUP BY a.difficulty
            """, (user_id,))
            difficulty_stats = await cursor.fetchall()

            return {
                'total_assignments': stats[0] if stats else 0,
                'graded_assignments': stats[1] if stats else 0,
                'avg_percentage': round(stats[2], 1) if stats and stats[2] else 0,
                'difficulty_stats': {row[0]: {'count': row[1], 'avg_percentage': round(row[2], 1) if row[2] else 0}
                                     for row in difficulty_stats}
            }