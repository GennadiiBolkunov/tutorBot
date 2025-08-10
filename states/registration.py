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

class AssignmentStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_grade = State()
    waiting_for_difficulty = State()
    waiting_for_due_date = State()

class SolutionStates(StatesGroup):
    waiting_for_solution = State()

class GradingStates(StatesGroup):
    waiting_for_score = State()
    waiting_for_comment = State()

class FileStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_assignment_files = State()
    waiting_for_solution_files = State()
    waiting_for_grade_files = State()