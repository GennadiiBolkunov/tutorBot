# states/registration.py
from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_last_name = State()
    waiting_for_phone = State()
    waiting_for_grade = State()
    waiting_for_parent_contact = State()
    waiting_for_motivation = State()

class AdminStates(StatesGroup):
    waiting_for_admin_decision = State()
    waiting_for_rejection_reason = State()