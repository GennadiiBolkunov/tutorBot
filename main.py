# main.py
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import os
import asyncio
import logging
from dotenv import load_dotenv

from database.db_handler import DatabaseHandler
from states.registration import RegistrationStates, AdminStates, AssignmentStates, SolutionStates, GradingStates
from handlers.assignments import (
    create_assignment_command, process_assignment_title, process_assignment_description,
    process_assignment_grade, process_difficulty_choice, process_due_date,
    show_all_assignments, show_my_assignments, show_assignment_detail,
    start_solution_submission, process_solution_submission,
    show_ungraded_solutions, view_solution_detail, start_grading,
    process_grading_score, process_grading_comment, show_my_progress,
    notify_students_new_assignment, notify_admin_new_solution, notify_student_grade
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Добавьте ваш telegram_id в .env

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = DatabaseHandler()


# === КОМАНДЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ===

@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id

    # Проверяем статус пользователя
    if await db.is_admin(user_id):
        await message.answer(
            "👨‍🏫 Добро пожаловать, администратор!\n\n"
            "Доступные команды:\n"
            "/pending - заявки на регистрацию\n"
            "/users - список учеников\n"
            "/create_assignment - создать задание\n"
            "/assignments - все задания\n"
            "/ungraded - непроверенные решения\n"
            "/help - справка"
        )
    elif await db.is_user_registered(user_id):
        user_data = await db.get_user(user_id)
        await message.answer(
            f"👋 Привет, {user_data['first_name']}!\n\n"
            "Вы уже зарегистрированы в системе.\n"
            "/assignments - мои задания\n"
            "/progress - моя статистика\n"
            "/profile - мой профиль\n"
            "/help - справка"
        )
    elif await db.has_pending_request(user_id):
        await message.answer(
            "⏳ Ваша заявка на регистрацию уже отправлена и ожидает рассмотрения.\n"
            "Администратор свяжется с вами после проверки."
        )
    else:
        await message.answer(
            "🎓 Добро пожаловать на занятия к Анастасии Ракитиной!\n\n"
            "Для получения доступа к системе необходимо зарегистрироваться.\n"
            "Ваша заявка будет рассмотрена администратором.\n\n"
            "Нажмите /register для подачи заявки"
        )


@dp.message(Command("register"))
async def register_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if await db.is_user_registered(user_id):
        await message.answer("✅ Вы уже зарегистрированы!")
        return

    if await db.has_pending_request(user_id):
        await message.answer("⏳ Ваша заявка уже отправлена и ожидает рассмотрения.")
        return

    # Сохраняем базовые данные из Telegram
    await state.update_data(
        telegram_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    await message.answer(
        f"📝 Начинаем регистрацию, {message.from_user.first_name}!\n\n"
        "Введите вашу фамилию:"
    )
    await state.set_state(RegistrationStates.waiting_for_last_name)


@dp.message(StateFilter(RegistrationStates.waiting_for_last_name))
async def process_last_name(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❌ Пожалуйста, введите корректную фамилию (минимум 2 символа):")
        return

    await state.update_data(last_name=message.text.strip())
    await message.answer("📱 Введите ваш номер телефона (для связи):")
    await state.set_state(RegistrationStates.waiting_for_phone)


@dp.message(StateFilter(RegistrationStates.waiting_for_phone))
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if len(phone) < 10:
        await message.answer("❌ Пожалуйста, введите корректный номер телефона:")
        return

    await state.update_data(phone=phone)
    await message.answer("🎓 Укажите ваш класс (число от 1 до 11):")
    await state.set_state(RegistrationStates.waiting_for_grade)


@dp.message(StateFilter(RegistrationStates.waiting_for_grade))
async def process_grade(message: types.Message, state: FSMContext):
    try:
        grade = int(message.text)
        if not 1 <= grade <= 11:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число от 1 до 11:")
        return

    await state.update_data(grade=grade)
    await message.answer(
        "👨‍👩‍👧‍👦 Введите контактные данные родителей\n"
        "(имя и телефон для связи):"
    )
    await state.set_state(RegistrationStates.waiting_for_parent_contact)


@dp.message(StateFilter(RegistrationStates.waiting_for_parent_contact))
async def process_parent_contact(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 5:
        await message.answer("❌ Пожалуйста, введите контактные данные родителей:")
        return

    await state.update_data(parent_contact=message.text.strip())
    await message.answer(
        "💭 Расскажите кратко, зачем вам нужны занятия по математике?\n"
        "(подготовка к экзаменам, улучшение оценок, изучение сложных тем и т.д.)"
    )
    await state.set_state(RegistrationStates.waiting_for_motivation)


@dp.message(StateFilter(RegistrationStates.waiting_for_motivation))
async def process_motivation(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 10:
        await message.answer("❌ Пожалуйста, напишите более подробно (минимум 10 символов):")
        return

    # Получаем все данные
    data = await state.get_data()
    data['motivation'] = message.text.strip()

    # Сохраняем заявку в базу данных
    success = await db.create_registration_request(
        telegram_id=data['telegram_id'],
        username=data.get('username'),
        first_name=data['first_name'],
        last_name=data['last_name'],
        phone=data['phone'],
        grade=data['grade'],
        parent_contact=data['parent_contact'],
        motivation=data['motivation']
    )

    if success:
        await message.answer(
            "✅ Заявка успешно отправлена!\n\n"
            "📋 Ваши данные:\n"
            f"Имя: {data['first_name']} {data['last_name']}\n"
            f"Класс: {data['grade']}\n"
            f"Телефон: {data['phone']}\n\n"
            "⏳ Ожидайте рассмотрения заявки администратором."
        )

        # Уведомляем администратора
        await notify_admin_new_request(data)
    else:
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

    await state.clear()


# === КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА ===

@dp.message(Command("pending"))
async def show_pending_requests(message: types.Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    requests = await db.get_pending_requests()

    if not requests:
        await message.answer("📋 Нет ожидающих заявок.")
        return

    for req in requests:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{req['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{req['id']}")
            ]
        ])

        text = (
            f"📋 Заявка #{req['id']}\n"
            f"👤 {req['first_name']} {req['last_name']}\n"
            f"🎓 Класс: {req['grade']}\n"
            f"📱 Телефон: {req['phone']}\n"
            f"👨‍👩‍👧‍👦 Родители: {req['parent_contact']}\n"
            f"💭 Мотивация: {req['motivation']}\n"
            f"📅 Дата заявки: {req['request_date'][:16]}"
        )

        await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("approve_"))
async def approve_request(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен.")
        return

    request_id = int(callback.data.split("_")[1])

    # Получаем данные заявки для уведомления
    requests = await db.get_pending_requests()
    request_data = next((r for r in requests if r['id'] == request_id), None)

    if request_data and await db.approve_registration(request_id, "Одобрено администратором"):
        await callback.message.edit_text(
            f"✅ Заявка #{request_id} одобрена!\n"
            f"Пользователь {request_data['first_name']} {request_data['last_name']} зарегистрирован."
        )

        # Уведомляем пользователя
        try:
            await bot.send_message(
                request_data['telegram_id'],
                "🎉 Поздравляем! Ваша заявка одобрена!\n\n"
                "Теперь вы можете пользоваться всеми функциями бота.\n"
                "Введите /help для просмотра доступных команд."
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить пользователя {request_data['telegram_id']}: {e}")
    else:
        await callback.answer("❌ Ошибка при обработке заявки.")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_request(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен.")
        return

    request_id = int(callback.data.split("_")[1])
    await state.update_data(reject_request_id=request_id)

    await callback.message.answer("📝 Введите причину отклонения заявки:")
    await state.set_state(AdminStates.waiting_for_rejection_reason)


@dp.message(StateFilter(AdminStates.waiting_for_rejection_reason))
async def process_rejection_reason(message: types.Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    request_id = data['reject_request_id']
    reason = message.text.strip()

    # Получаем данные заявки
    requests = await db.get_pending_requests()
    request_data = next((r for r in requests if r['id'] == request_id), None)

    if request_data and await db.reject_registration(request_id, reason):
        await message.answer(f"❌ Заявка #{request_id} отклонена.")

        # Уведомляем пользователя
        try:
            await bot.send_message(
                request_data['telegram_id'],
                f"😔 К сожалению, ваша заявка была отклонена.\n\n"
                f"Причина: {reason}\n\n"
                "Вы можете подать новую заявку, исправив указанные недочеты."
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить пользователя {request_data['telegram_id']}: {e}")
    else:
        await message.answer("❌ Ошибка при отклонении заявки.")

    await state.clear()


@dp.message(Command("users"))
async def show_users(message: types.Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    users = await db.get_all_users()

    if not users:
        await message.answer("📋 Нет зарегистрированных пользователей.")
        return

    text = "👥 Зарегистрированные ученики:\n\n"
    for user in users:
        text += (
            f"👤 {user['first_name']} {user['last_name']}\n"
            f"🎓 Класс: {user['grade']}\n"
            f"📱 {user['phone']}\n"
            f"📅 Регистрация: {user['registration_date'][:10]}\n\n"
        )

    # Разбиваем на части если текст слишком длинный
    if len(text) > 4000:
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)


# === КОМАНДЫ ДЛЯ СИСТЕМЫ ЗАДАНИЙ ===

# Команды для администратора
@dp.message(Command("create_assignment"))
async def create_assignment_handler(message: types.Message, state: FSMContext):
    await create_assignment_command(message, state)


@dp.message(StateFilter(AssignmentStates.waiting_for_title))
async def assignment_title_handler(message: types.Message, state: FSMContext):
    await process_assignment_title(message, state)


@dp.message(StateFilter(AssignmentStates.waiting_for_description))
async def assignment_description_handler(message: types.Message, state: FSMContext):
    await process_assignment_description(message, state)


@dp.message(StateFilter(AssignmentStates.waiting_for_grade))
async def assignment_grade_handler(message: types.Message, state: FSMContext):
    await process_assignment_grade(message, state)


@dp.callback_query(F.data.startswith("difficulty_"))
async def difficulty_handler(callback: CallbackQuery, state: FSMContext):
    await process_difficulty_choice(callback, state)


@dp.message(StateFilter(AssignmentStates.waiting_for_due_date))
async def due_date_handler(message: types.Message, state: FSMContext):
    # Получаем все данные и создаем задание
    data = await state.get_data()
    due_date = None

    if message.text.lower() not in ['нет', 'no', 'skip', '-']:
        try:
            # Парсим дату
            from datetime import datetime
            date_str = message.text.strip()
            due_date = datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            await message.answer("❌ Неверный формат даты. Попробуйте ДД.ММ.ГГГГ или напишите 'нет':")
            return

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
    notification_data = await notify_students_new_assignment(assignment_id, data)
    if notification_data:
        await send_assignment_notifications(notification_data)

    await state.clear()


@dp.message(Command("assignments"))
async def assignments_handler(message: types.Message):
    if await db.is_admin(message.from_user.id):
        await show_all_assignments(message)
    else:
        await show_my_assignments(message)


@dp.message(Command("assignment"))
async def assignment_detail_handler(message: types.Message):
    await show_assignment_detail(message)


@dp.message(Command("ungraded"))
async def ungraded_handler(message: types.Message):
    await show_ungraded_solutions(message)


# Команды для учеников
@dp.message(Command("progress"))
async def progress_handler(message: types.Message):
    await show_my_progress(message)


# Callback handlers для заданий
@dp.callback_query(F.data.startswith("solve_"))
async def solve_handler(callback: CallbackQuery, state: FSMContext):
    await start_solution_submission(callback, state)


@dp.message(StateFilter(SolutionStates.waiting_for_solution))
async def solution_handler(message: types.Message, state: FSMContext):
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
    notification_data = await notify_admin_new_solution(user_id, assignment_id, result_id)
    if notification_data:
        await send_solution_notification(notification_data)

    await state.clear()


@dp.callback_query(F.data.startswith("view_solution_"))
async def view_solution_handler(callback: CallbackQuery):
    await view_solution_detail(callback)


@dp.callback_query(F.data.startswith("grade_"))
async def grade_handler(callback: CallbackQuery, state: FSMContext):
    await start_grading(callback, state)


@dp.message(StateFilter(GradingStates.waiting_for_score))
async def grading_score_handler(message: types.Message, state: FSMContext):
    await process_grading_score(message, state)


@dp.message(StateFilter(GradingStates.waiting_for_comment))
async def grading_comment_handler(message: types.Message, state: FSMContext):
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
        notification_data = await notify_student_grade(solution_id, score, max_score, comment)
        if notification_data:
            await send_grade_notification(notification_data)
    else:
        await message.answer("❌ Ошибка при выставлении оценки.")

    await state.clear()


@dp.message(Command("help"))
async def help_command(message: types.Message):
    user_id = message.from_user.id

    if await db.is_admin(user_id):
        text = (
            "🔧 Команды администратора:\n\n"
            "👥 Управление пользователями:\n"
            "/pending - заявки на регистрацию\n"
            "/users - список учеников\n\n"
            "📚 Управление заданиями:\n"
            "/create_assignment - создать задание\n"
            "/assignments - все задания\n"
            "/ungraded - непроверенные решения\n\n"
            "/help - эта справка"
        )
    elif await db.is_user_registered(user_id):
        text = (
            "📚 Доступные команды:\n\n"
            "/assignments - мои задания\n"
            "/assignment <ID> - детали задания\n"
            "/progress - моя статистика\n"
            "/profile - мой профиль\n"
            "/help - эта справка"
        )
    else:
        text = (
            "ℹ️ Доступные команды:\n\n"
            "/start - начать работу\n"
            "/register - подать заявку на регистрацию\n"
            "/help - эта справка"
        )

    await message.answer(text)


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def send_assignment_notifications(notification_data):
    """Отправить уведомления о новом задании"""
    difficulty_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}

    for user in notification_data['target_users']:
        try:
            text = (
                f"🆕 Новое задание!\n\n"
                f"📝 {notification_data['title']}\n"
                f"⚡ Сложность: {difficulty_emoji.get(notification_data['difficulty'], '⚡')} {notification_data['difficulty']}\n\n"
                f"Посмотреть: /assignment {notification_data['assignment_id']}"
            )
            await bot.send_message(user['telegram_id'], text)
        except Exception as e:
            logging.error(f"Не удалось уведомить пользователя {user['telegram_id']}: {e}")


async def send_solution_notification(notification_data):
    """Отправить уведомление админу о новом решении"""
    try:
        text = (
            f"📤 Новое решение!\n\n"
            f"👤 {notification_data['user_data']['first_name']} {notification_data['user_data']['last_name']} "
            f"({notification_data['user_data']['grade']} класс)\n"
            f"📝 Задание: {notification_data['assignment']['title']}\n"
            f"🆔 ID решения: {notification_data['result_id']}\n\n"
            "Используйте /ungraded для проверки."
        )

        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logging.error(f"Ошибка при уведомлении админа: {e}")


async def send_grade_notification(notification_data):
    """Отправить уведомление ученику об оценке"""
    try:
        grade_emoji = "🟢" if notification_data['percentage'] >= 80 else "🟡" if notification_data[
                                                                                   'percentage'] >= 60 else "🔴"

        text = (
            f"{grade_emoji} Ваше решение проверено!\n\n"
            f"📝 Задание: {notification_data['assignment_title']}\n"
            f"📊 Оценка: {notification_data['score']}/{notification_data['max_score']} ({notification_data['percentage']}%)\n"
        )

        if notification_data['comment']:
            text += f"💬 Комментарий: {notification_data['comment']}\n"

        text += "\nПосмотреть все результаты: /progress"

        await bot.send_message(notification_data['user_id'], text)
    except Exception as e:
        logging.error(f"Ошибка при уведомлении ученика: {e}")


async def notify_admin_new_request(request_data):
    """Уведомляем администратора о новой заявке"""
    try:
        text = (
            "🔔 Новая заявка на регистрацию!\n\n"
            f"👤 {request_data['first_name']} {request_data['last_name']}\n"
            f"🎓 Класс: {request_data['grade']}\n"
            f"📱 Телефон: {request_data['phone']}\n\n"
            "Используйте /pending для просмотра всех заявок."
        )
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logging.error(f"Не удалось уведомить администратора: {e}")


async def main():
    # Инициализируем базу данных
    await db.init_db()

    # Добавляем главного администратора
    await db.add_admin(ADMIN_ID, "admin", "Администратор", is_super_admin=True)

    print("🤖 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())