from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    """Used for both paid booking and free episode — lead_type stored in FSM data."""
    name         = State()
    content_type = State()
    date         = State()
    time         = State()
    hours        = State()
    phone        = State()


class BroadcastForm(StatesGroup):
    target  = State()
    message = State()
    confirm = State()


class AdminAction(StatesGroup):
    payment_amount    = State()
    payment_hours     = State()
    no_pay_reason     = State()
    reschedule_reason = State()
    reschedule_date   = State()
    reschedule_time   = State()   # renamed: was reschedule_hours, now collects start time


class EditContentFSM(StatesGroup):
    edit_text  = State()
    edit_photo = State()
