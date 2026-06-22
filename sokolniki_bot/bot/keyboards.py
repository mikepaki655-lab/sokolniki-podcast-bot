from datetime import date, timedelta

from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS   = ["янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек"]


# ─── USER MAIN MENU ───────────────────────────────────────────────────────────

def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🏠 Забронировать студию"))
    builder.row(
        KeyboardButton(text="💰 Узнать цены"),
        KeyboardButton(text="📍 Адрес студии"),
    )
    return builder.as_markup(resize_keyboard=True)


# ─── ADMIN REPLY MENUS ────────────────────────────────────────────────────────

def admin_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📋 Заявки"))
    builder.row(
        KeyboardButton(text="📨 Рассылка"),
        KeyboardButton(text="📊 Аналитика"),
    )
    builder.row(KeyboardButton(text="📝 Контент"))
    builder.row(KeyboardButton(text="◀️ Вернуться в бота"))
    return builder.as_markup(resize_keyboard=True)


def admin_bookings_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🆕 Новые"),
        KeyboardButton(text="⚙️ В обработке"),
    )
    builder.row(KeyboardButton(text="✅ Завершённые"))
    builder.row(KeyboardButton(text="◀️ Назад к меню"))
    return builder.as_markup(resize_keyboard=True)


def admin_broadcast_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📤 Всем"),
        KeyboardButton(text="📤 Новым"),
    )
    builder.row(
        KeyboardButton(text="📤 В обработке"),
        KeyboardButton(text="📤 Завершённым"),
    )
    builder.row(KeyboardButton(text="◀️ Назад к меню"))
    return builder.as_markup(resize_keyboard=True)


# ─── BOOKING INLINE ───────────────────────────────────────────────────────────

def content_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label in ["🎙 Подкаст", "🎬 Видео", "📱 Рилс/Шортс", "✏️ Другое"]:
        builder.button(text=label, callback_data=f"ctype:{label}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def dates_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = date.today()
    for i in range(14):
        d = today + timedelta(days=i)
        label = f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
        value = d.strftime("%d.%m.%Y")
        builder.button(text=label, callback_data=f"bdate:{value}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(3)
    return builder.as_markup()


def times_kb(blocked: set[int] | None = None) -> InlineKeyboardMarkup:
    """00:00–23:00, skips blocked hours."""
    blocked = blocked or set()
    builder = InlineKeyboardBuilder()
    free = [h for h in range(24) if h not in blocked]
    if free:
        for h in free:
            builder.button(text=f"{h:02d}:00", callback_data=f"btime:{h:02d}:00")
    else:
        builder.button(text="⛔ Нет свободных слотов", callback_data="no_slots")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(4)
    return builder.as_markup()


def hours_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for h in range(1, 13):
        builder.button(text=f"{h} ч", callback_data=f"bhours:{h}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(4)
    return builder.as_markup()


# ─── PHONE REQUEST (Reply Keyboard) ──────────────────────────────────────────

def phone_request_kb() -> ReplyKeyboardMarkup:
    """Native Telegram contact-sharing button + text fallback."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📱 Поделиться номером", request_contact=True))
    builder.row(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


# ─── ADMIN INLINE BOOKING ACTIONS ─────────────────────────────────────────────

def new_booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить бронирование", callback_data=f"bstatus:{booking_id}:confirmed")
    builder.adjust(1)
    return builder.as_markup()


def processing_booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Завершена с оплатой",  callback_data=f"bstatus:{booking_id}:done_paid")
    builder.button(text="❌ Завершена без оплаты", callback_data=f"bstatus:{booking_id}:done_no_pay")
    builder.button(text="🔄 Перенести",            callback_data=f"bstatus:{booking_id}:reschedule")
    builder.adjust(1)
    return builder.as_markup()


# ─── BROADCAST / CONTENT / MISC ───────────────────────────────────────────────

def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm:yes")
    builder.button(text="❌ Отмена",    callback_data="broadcast_confirm:no")
    builder.adjust(2)
    return builder.as_markup()


def content_sections_kb(sections: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sections:
        builder.button(text=s.title, callback_data=f"content:section:{s.key}")
    builder.adjust(1)
    return builder.as_markup()


def content_edit_kb(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить текст", callback_data=f"content:edit_text:{key}")
    builder.button(text="🖼 Изменить фото",  callback_data=f"content:edit_photo:{key}")
    builder.button(text="👁 Предпросмотр",   callback_data=f"content:preview:{key}")
    builder.adjust(1)
    return builder.as_markup()


def content_back_to_section_kb(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=f"content:section:{key}")
    return builder.as_markup()


def prices_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Записаться", callback_data="go_booking")
    return builder.as_markup()



def slot_conflict_kb(max_hours: int = 0) -> InlineKeyboardMarkup:
    """Buttons shown when chosen time+duration overlaps an existing booking."""
    builder = InlineKeyboardBuilder()
    if max_hours > 0:
        noun = "час" if max_hours == 1 else "часа" if max_hours < 5 else "часов"
        builder.button(text=f"✅ Взять {max_hours} {noun}", callback_data=f"bhours:{max_hours}")
    builder.button(text="🕐 Другое время", callback_data="back_to_time")
    builder.button(text="📅 Другая дата",  callback_data="back_to_date")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
