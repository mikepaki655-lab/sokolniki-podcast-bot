from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    name         = State()
    content_type = State()
    date         = State()
    time         = State()
    hours        = State()


class FreeEpisodeForm(StatesGroup):
    name         = State()
    phone        = State()
    social_link  = State()
    occupation   = State()
    podcast_goal = State()


class BroadcastForm(StatesGroup):
    target  = State()
    message = State()
    confirm = State()


class PaymentForm(StatesGroup):
    amount = State()


class EditContent(StatesGroup):
    choose_section = State()
    choose_field   = State()
    edit_text      = State()
    edit_photo     = State()
