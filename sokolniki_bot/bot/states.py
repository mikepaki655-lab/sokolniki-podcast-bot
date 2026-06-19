from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    name         = State()
    content_type = State()
    date         = State()
    time         = State()
    hours        = State()
    phone        = State()


class FreeEpisodeForm(StatesGroup):
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
    payment_amount   = State()
    payment_hours    = State()
    no_pay_reason    = State()
    reschedule_reason = State()
    reschedule_date  = State()
    reschedule_hours = State()


class AnalyticsPeriod(StatesGroup):
    custom_start = State()
    custom_end   = State()
