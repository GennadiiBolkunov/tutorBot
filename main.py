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
from states.registration import RegistrationStates, AdminStates

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
            "/pending - посмотреть заявки на регистрацию\n"
            "/users - список учеников\n"
            "/help - справка"
        )
    elif await db.is_user_registered(user_id):
        user_data = await db.get_user(user_id)
        await message.answer(
            f"👋 Привет, {user_data['first_name']}!\n\n"
            "Вы уже зарегистрированы в системе.\n"
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


@dp.message(Command("help"))
async def help_command(message: types.Message):
    user_id = message.from_user.id

    if await db.is_admin(user_id):
        text = (
            "🔧 Команды администратора:\n\n"
            "/pending - заявки на регистрацию\n"
            "/users - список учеников\n"
            "/help - эта справка"
        )
    elif await db.is_user_registered(user_id):
        text = (
            "📚 Доступные команды:\n\n"
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