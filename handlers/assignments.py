# handlers/assignments.py
from aiogram import types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from datetime import datetime, timedelta
import aiosqlite

from database.db_handler import DatabaseHandler
from states.registration import AssignmentStates, SolutionStates, GradingStates

db = DatabaseHandler()


# === КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА ===

async def create_assignment_command(message: types.Message, state: FSMContext):
    """Команда создания нового задания"""
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    await message.answer("📝 Создание нового задания\n\nВведите название задания:")
    await state.set_state(AssignmentStates.waiting_for_title)


async def process_assignment_title(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("❌ Название должно содержать минимум 3 символа:")
        return

    await state.update_data(title=message.text.strip())
    await message.answer("📄 Введите описание задания (условие, что нужно сделать):")
    await state.set_state(AssignmentStates.waiting_for_description)


async def process_assignment_description(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 10:
        await message.answer("❌ Описание должно содержать минимум 10 символов:")
        return

    await state.update_data(description=message.text.strip())
    await message.answer(
        "🎓 Для какого класса задание?\n\n"
        "Введите номер класса (1-11) или 0 для всех классов:"
    )
    await state.set_state(AssignmentStates.waiting_for_grade)


async def process_assignment_grade(message: types.Message, state: FSMContext):
    try:
        grade = int(message.text)
        if not 0 <= grade <= 11:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 0 до 11 (0 = для всех классов):")
        return

    await state.update_data(grade_level=grade)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Легко", callback_data="difficulty_easy"),
            InlineKeyboardButton(text="🟡 Средне", callback_data="difficulty_medium"),
            InlineKeyboardButton(text="🔴 Сложно", callback_data="difficulty_hard")
        ]
    ])

    await message.answer("⚡ Выберите сложность задания:", reply_markup=keyboard)


async def process_difficulty_choice(callback: CallbackQuery, state: FSMContext):
    difficulty_map = {
        "difficulty_easy": "easy",
        "difficulty_medium": "medium",
        "difficulty_hard": "hard"
    }

    difficulty = difficulty_map.get(callback.data)
    if not difficulty:
        return

    await state.update_data(difficulty=difficulty)
    await callback.message.edit_text(
        f"✅ Сложность: {difficulty}\n\n"
        "📅 Установить срок сдачи? (необязательно)\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ или напишите 'нет' чтобы пропустить:"
    )
    await state.set_state(AssignmentStates.waiting_for_due_date)


async def process_due_date(message: types.Message, state: FSMContext):
    due_date = None

    if message.text.lower() not in ['нет', 'no', 'skip', '-']:
        try:
            # Парсим дату
            date_str = message.text.strip()
            due_date = datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            await message.answer("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ или напишите 'нет':")
            return

    # Получаем все данные и создаем задание
    data = await state.get_data()

    assignment_id = await db.create_assignment(
        title=data['title'],
        description=data['description'],
        grade_level=data['grade_level'],
        difficulty=data['difficulty'],
        created_by=message.from_user.id,
        due_date=due_date
    )

    grade_text = f"класс {data['grade_level']}" if data['grade_level'] > 0 else "все классы"
    due_text = f"\n📅 Срок: {due_date[:10]}" if due_date else ""

    await message.answer(
        f"✅ Задание создано!\n\n"
        f"📝 Название: {data['title']}\n"
        f"🎓 Для: {grade_text}\n"
        f"⚡ Сложность: {data['difficulty']}{due_text}\n\n"
        f"ID задания: {assignment_id}"
    )

    # Уведомляем учеников о новом задании
    from handlers.assignments import notify_students_new_assignment
    notification_data = await notify_students_new_assignment(assignment_id, data)

    await state.clear()

    return notification_data  # Возвращаем для обработки в main


async def show_all_assignments(message: types.Message):
    """Показать все задания (для админа)"""
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    assignments = await db.get_all_assignments()

    if not assignments:
        await message.answer("📋 Заданий пока нет.\n\nИспользуйте /create_assignment для создания.")
        return

    text = "📚 Все задания:\n\n"
    for assignment in assignments:
        status = "✅ Активно" if assignment['is_active'] else "❌ Неактивно"
        grade_text = f"класс {assignment['grade_level']}" if assignment['grade_level'] > 0 else "все классы"
        due_text = f" (до {assignment['due_date'][:10]})" if assignment['due_date'] else ""

        text += (
            f"🆔 {assignment['id']} - {assignment['title']}\n"
            f"🎓 {grade_text} | ⚡ {assignment['difficulty']} | {status}{due_text}\n"
            f"📅 {assignment['created_date'][:10]}\n\n"
        )

    # Разбиваем на части если текст слишком длинный
    if len(text) > 4000:
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)


# === КОМАНДЫ ДЛЯ УЧЕНИКОВ ===

async def show_my_assignments(message: types.Message):
    """Показать доступные задания для ученика"""
    user_id = message.from_user.id

    if not await db.is_user_registered(user_id):
        await message.answer("❌ Вы не зарегистрированы в системе.")
        return

    user_data = await db.get_user(user_id)
    assignments = await db.get_assignments_for_grade(user_data['grade'])

    if not assignments:
        await message.answer("📋 Для вас пока нет доступных заданий.")
        return

    text = "📚 Доступные задания:\n\n"
    for assignment in assignments:
        due_text = f" 📅 до {assignment['due_date'][:10]}" if assignment['due_date'] else ""
        difficulty_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}

        text += (
            f"🆔 {assignment['id']} - {assignment['title']}\n"
            f"{difficulty_emoji.get(assignment['difficulty'], '⚡')} {assignment['difficulty']}{due_text}\n"
            f"📄 {assignment['description'][:100]}{'...' if len(assignment['description']) > 100 else ''}\n\n"
        )

    text += "Для просмотра задания: /assignment <ID>\nДля отправки решения: /solve <ID>"

    if len(text) > 4000:
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)


async def show_assignment_detail(message: types.Message):
    """Показать детали конкретного задания"""
    user_id = message.from_user.id

    if not await db.is_user_registered(user_id) and not await db.is_admin(user_id):
        await message.answer("❌ Доступ запрещен.")
        return

    try:
        # Извлекаем ID задания из команды
        assignment_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Используйте: /assignment <ID задания>")
        return

    assignment = await db.get_assignment_by_id(assignment_id)

    if not assignment:
        await message.answer("❌ Задание не найдено.")
        return

    # Проверяем доступ для ученика
    if not await db.is_admin(user_id):
        user_data = await db.get_user(user_id)
        if assignment['grade_level'] != 0 and assignment['grade_level'] != user_data['grade']:
            await message.answer("❌ Это задание не для вашего класса.")
            return

    difficulty_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
    grade_text = f"класс {assignment['grade_level']}" if assignment['grade_level'] > 0 else "все классы"
    due_text = f"\n📅 Срок сдачи: {assignment['due_date'][:16]}" if assignment['due_date'] else ""

    text = (
        f"📝 {assignment['title']}\n\n"
        f"📄 Описание:\n{assignment['description']}\n\n"
        f"🎓 Для: {grade_text}\n"
        f"⚡ Сложность: {difficulty_emoji.get(assignment['difficulty'], '⚡')} {assignment['difficulty']}\n"
        f"📅 Создано: {assignment['created_date'][:16]}{due_text}"
    )

    # Добавляем кнопки для действий
    if await db.is_admin(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Решения", callback_data=f"solutions_{assignment_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_assignment_{assignment_id}")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить решение", callback_data=f"solve_{assignment_id}")]
        ])

    await message.answer(text, reply_markup=keyboard)


async def start_solution_submission(callback: CallbackQuery, state: FSMContext):
    """Начать отправку решения"""
    assignment_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    if not await db.is_user_registered(user_id):
        await callback.answer("❌ Вы не зарегистрированы.")
        return

    assignment = await db.get_assignment_by_id(assignment_id)
    if not assignment:
        await callback.answer("❌ Задание не найдено.")
        return

    await state.update_data(assignment_id=assignment_id)
    await callback.message.edit_text(
        f"📝 Отправка решения для: {assignment['title']}\n\n"
        "Отправьте ваше решение текстом. Можете включить:\n"
        "• Подробное решение\n"
        "• Формулы и вычисления\n"
        "• Ответ\n"
        "• Объяснение хода решения"
    )
    await state.set_state(SolutionStates.waiting_for_solution)


async def process_solution_submission(message: types.Message, state: FSMContext):
    """Обработка отправленного решения"""
    if not message.text or len(message.text.strip()) < 10:
        await message.answer("❌ Решение должно содержать минимум 10 символов:")
        return

    data = await state.get_data()
    assignment_id = data['assignment_id']
    user_id = message.from_user.id

    result_id = await db.submit_solution(user_id, assignment_id, message.text.strip())
    assignment = await db.get_assignment_by_id(assignment_id)

    await message.answer(
        f"✅ Решение отправлено!\n\n"
        f"📝 Задание: {assignment['title']}\n"
        f"🆔 ID решения: {result_id}\n\n"
        "Ожидайте проверки преподавателем."
    )

    # Уведомляем админа о новом решении
    from handlers.assignments import notify_admin_new_solution
    notification_data = await notify_admin_new_solution(user_id, assignment_id, result_id)

    await state.clear()

    return notification_data  # Возвращаем для обработки в main


# === СИСТЕМА ОЦЕНИВАНИЯ ===

async def show_ungraded_solutions(message: types.Message):
    """Показать непроверенные решения"""
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    solutions = await db.get_ungraded_solutions()

    if not solutions:
        await message.answer("✅ Все решения проверены!")
        return

    for solution in solutions[:5]:  # Показываем по 5 за раз
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Оценить", callback_data=f"grade_{solution['id']}"),
                InlineKeyboardButton(text="👁 Просмотр", callback_data=f"view_solution_{solution['id']}")
            ]
        ])

        text = (
            f"📝 {solution['title']}\n"
            f"👤 {solution['first_name']} {solution['last_name']} ({solution['grade_level']} класс)\n"
            f"📅 Отправлено: {solution['completed_date'][:16]}\n"
            f"🆔 ID: {solution['id']}"
        )

        await message.answer(text, reply_markup=keyboard)

    if len(solutions) > 5:
        await message.answer(f"Показано 5 из {len(solutions)} решений.")


async def view_solution_detail(callback: CallbackQuery):
    """Просмотр детального решения"""
    solution_id = int(callback.data.split("_")[2])

    solutions = await db.get_ungraded_solutions()
    solution = next((s for s in solutions if s['id'] == solution_id), None)

    if not solution:
        await callback.answer("❌ Решение не найдено.")
        return

    text = (
        f"📝 {solution['title']}\n"
        f"👤 {solution['first_name']} {solution['last_name']}\n\n"
        f"📄 Решение:\n{solution['solution_text']}\n\n"
        f"📅 {solution['completed_date'][:16]}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оценить", callback_data=f"grade_{solution['id']}")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)


async def start_grading(callback: CallbackQuery, state: FSMContext):
    """Начать оценивание решения"""
    solution_id = int(callback.data.split("_")[1])

    await state.update_data(solution_id=solution_id)
    await callback.message.edit_text(
        "📊 Оценивание решения\n\n"
        "Введите оценку в формате: <балл>/<максимум>\n"
        "Например: 8/10 или 15/20"
    )
    await state.set_state(GradingStates.waiting_for_score)


async def process_grading_score(message: types.Message, state: FSMContext):
    """Обработка введенной оценки"""
    try:
        # Парсим оценку
        score_text = message.text.strip()
        if '/' not in score_text:
            raise ValueError

        score, max_score = map(int, score_text.split('/'))

        if score < 0 or max_score <= 0 or score > max_score:
            raise ValueError

    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: <балл>/<максимум> (например: 8/10)")
        return

    await state.update_data(score=score, max_score=max_score)
    await message.answer("💬 Введите комментарий к оценке (или напишите '-' чтобы пропустить):")
    await state.set_state(GradingStates.waiting_for_comment)


async def process_grading_comment(message: types.Message, state: FSMContext):
    """Обработка комментария к оценке"""
    comment = message.text.strip() if message.text.strip() != '-' else ""

    data = await state.get_data()
    solution_id = data['solution_id']
    score = data['score']
    max_score = data['max_score']

    success = await db.grade_solution(solution_id, score, max_score, comment)

    if success:
        percentage = round((score / max_score) * 100, 1)
        await message.answer(
            f"✅ Оценка выставлена!\n\n"
            f"📊 Результат: {score}/{max_score} ({percentage}%)\n"
            f"💬 Комментарий: {comment if comment else 'Без комментария'}"
        )

        # Уведомляем ученика о результате
        from handlers.assignments import notify_student_grade
        notification_data = await notify_student_grade(solution_id, score, max_score, comment)

        return notification_data  # Возвращаем для обработки в main
    else:
        await message.answer("❌ Ошибка при выставлении оценки.")

    await state.clear()


# === СТАТИСТИКА ДЛЯ УЧЕНИКОВ ===

async def show_my_progress(message: types.Message):
    """Показать прогресс ученика"""
    user_id = message.from_user.id

    if not await db.is_user_registered(user_id):
        await message.answer("❌ Вы не зарегистрированы в системе.")
        return

    solutions = await db.get_user_solutions(user_id)
    stats = await db.get_user_stats(user_id)

    if not solutions:
        await message.answer("📊 У вас пока нет отправленных решений.")
        return

    # Общая статистика
    text = (
        f"📊 Ваша статистика\n\n"
        f"📝 Всего заданий: {stats['total_assignments']}\n"
        f"✅ Проверено: {stats['graded_assignments']}\n"
        f"📈 Средний балл: {stats['avg_percentage']}%\n\n"
    )

    # Статистика по сложности
    if stats['difficulty_stats']:
        text += "📊 По уровням сложности:\n"
        difficulty_names = {"easy": "🟢 Легко", "medium": "🟡 Средне", "hard": "🔴 Сложно"}
        for difficulty, data in stats['difficulty_stats'].items():
            name = difficulty_names.get(difficulty, difficulty)
            text += f"{name}: {data['avg_percentage']}% ({data['count']} заданий)\n"
        text += "\n"

    # Последние решения
    text += "📋 Последние решения:\n"
    for solution in solutions[:5]:
        status = "⏳ На проверке" if solution['score'] is None else f"✅ {solution['score']}/{solution['max_score']}"
        text += f"• {solution['title']} - {status}\n"

    if len(solutions) > 5:
        text += f"\nИ еще {len(solutions) - 5} решений..."

    await message.answer(text)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def notify_students_new_assignment(assignment_id: int, assignment_data: dict):
    """Уведомить учеников о новом задании"""
    try:
        # Получаем учеников для этого класса
        all_users = await db.get_all_users()
        target_users = []

        if assignment_data['grade_level'] == 0:
            target_users = all_users  # Для всех классов
        else:
            target_users = [u for u in all_users if u['grade'] == assignment_data['grade_level']]

        difficulty_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
        notification_data = {
            'assignment_id': assignment_id,
            'title': assignment_data['title'],
            'difficulty': assignment_data['difficulty'],
            'target_users': target_users
        }

        # Возвращаем данные для уведомления, которые обработает основной код
        return notification_data

    except Exception as e:
        print(f"Ошибка при подготовке уведомления о новом задании: {e}")
        return None


async def notify_admin_new_solution(user_id: int, assignment_id: int, result_id: int):
    """Подготовить данные для уведомления админа о новом решении"""
    try:
        user_data = await db.get_user(user_id)
        assignment = await db.get_assignment_by_id(assignment_id)

        return {
            'user_data': user_data,
            'assignment': assignment,
            'result_id': result_id
        }
    except Exception as e:
        print(f"Ошибка при подготовке уведомления админа: {e}")
        return None


async def notify_student_grade(solution_id: int, score: int, max_score: int, comment: str):
    """Подготовить данные для уведомления ученика о результате"""
    try:
        # Получаем данные решения через прямой запрос к базе
        async with aiosqlite.connect(db.db_path) as conn:
            cursor = await conn.execute("""
                SELECT r.user_id, a.title
                FROM results r
                JOIN assignments a ON r.assignment_id = a.id
                WHERE r.id = ?
            """, (solution_id,))
            result = await cursor.fetchone()

        if result:
            user_id, assignment_title = result
            percentage = round((score / max_score) * 100, 1)

            return {
                'user_id': user_id,
                'assignment_title': assignment_title,
                'score': score,
                'max_score': max_score,
                'percentage': percentage,
                'comment': comment
            }

    except Exception as e:
        print(f"Ошибка при подготовке уведомления ученика: {e}")
        return None