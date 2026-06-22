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
    builder.row(KeyboardButton(text="📅 Мои брони"))
    builder.row(KeyboardButton(text="📩 Написать нам"))
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
    builder.row(KeyboardButton(text="🔧 Управление Админкой"))
    builder.row(KeyboardButton(text="◀️ Вернуться в бота"))
    return builder.as_markup(resize_keyboard=True)


def manage_admins_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить Админа", callback_data="admin_manage:add")
    builder.button(text="❌ Удалить Админа",  callback_data="admin_manage:remove")
    builder.adjust(1)
    return builder.as_markup()


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


def times_kb(blocked: set[int] | None = None, min_hour: int = 0) -> InlineKeyboardMarkup:
    """00:00–23:00, skips blocked hours and hours before min_hour."""
    blocked = blocked or set()
    builder = InlineKeyboardBuilder()
    free = [h for h in range(max(0, min_hour), 24) if h not in blocked]
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
    builder.button(text="🗑 Удалить заявку",           callback_data=f"del_booking:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def processing_booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Завершена с оплатой",  callback_data=f"bstatus:{booking_id}:done_paid")
    builder.button(text="❌ Завершена без оплаты", callback_data=f"bstatus:{booking_id}:done_no_pay")
    builder.button(text="🔄 Перенести",            callback_data=f"bstatus:{booking_id}:reschedule")
    builder.button(text="🗑 Удалить заявку",        callback_data=f"del_booking:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def done_booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить заявку", callback_data=f"del_booking:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить",   callback_data=f"del_booking_confirm:{booking_id}")
    builder.button(text="❌ Нет, оставить", callback_data=f"view_booking:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


# ─── MY BOOKINGS (CLIENT) ──────────────────────────────────────────────────────

def my_bookings_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Активные",    callback_data="my_bookings:active")
    builder.button(text="✅ Завершённые", callback_data="my_bookings:done")
    builder.adjust(1)
    return builder.as_markup()


def my_booking_item_kb(
    booking_id: int,
    can_cancel: bool = True,
    can_reschedule: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_reschedule:
        builder.button(text="📅 Перенести",             callback_data=f"reschedule_booking:{booking_id}")
    if can_cancel:
        builder.button(text="❌ Отменить бронирование", callback_data=f"cancel_booking:{booking_id}")
    builder.button(text="◀️ Назад", callback_data="my_bookings:active")
    builder.adjust(1)
    return builder.as_markup()


def reschedule_dates_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = date.today()
    for i in range(14):
        d = today + timedelta(days=i)
        label = f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"
        value = d.strftime("%d.%m.%Y")
        builder.button(text=label, callback_data=f"rs_date:{value}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(3)
    return builder.as_markup()


def reschedule_times_kb(blocked: set[int] | None = None, min_hour: int = 0) -> InlineKeyboardMarkup:
    blocked = blocked or set()
    builder = InlineKeyboardBuilder()
    free = [h for h in range(max(0, min_hour), 24) if h not in blocked]
    if free:
        for h in free:
            builder.button(text=f"{h:02d}:00", callback_data=f"rs_time:{h:02d}:00")
    else:
        builder.button(text="⛔ Нет свободных слотов", callback_data="no_slots")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(4)
    return builder.as_markup()


def reschedule_hours_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for h in range(1, 13):
        builder.button(text=f"{h} ч", callback_data=f"rs_hours:{h}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(4)
    return builder.as_markup()


def reschedule_slot_conflict_kb(available_hours: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if available_hours > 0:
        noun = "час" if available_hours == 1 else "часа" if available_hours < 5 else "часов"
        builder.button(
            text=f"✅ Взять {available_hours} {noun}",
            callback_data=f"rs_hours:{available_hours}",
        )
    builder.button(text="🕐 Другое время", callback_data="rs_back_to_time")
    builder.button(text="📅 Другая дата",  callback_data="rs_back_to_date")
    builder.adjust(1)
    return builder.as_markup()


def reschedule_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить перенос", callback_data=f"reschedule_confirm_yes:{booking_id}")
    builder.button(text="❌ Отмена",               callback_data=f"reschedule_confirm_no:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def my_booking_done_item_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="my_bookings:done")
    return builder.as_markup()


def confirm_client_cancel_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, отменить",  callback_data=f"cancel_booking_yes:{booking_id}")
    builder.button(text="◀️ Нет, оставить", callback_data=f"my_booking_detail:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def skip_reason_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Пропустить", callback_data="cancel_reason_skip")
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


# ─── MISC ─────────────────────────────────────────────────────────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def remove_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardRemove()


def prices_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Забронировать студию", callback_data="go_booking")
    return builder.as_markup()


def slot_conflict_kb(available_hours: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if available_hours > 0:
        noun = "час" if available_hours == 1 else "часа" if available_hours < 5 else "часов"
        builder.button(
            text=f"✅ Взять {available_hours} {noun}",
            callback_data=f"bhours:{available_hours}",
        )
    builder.button(text="🕐 Другое время", callback_data="back_to_time")
    builder.button(text="📅 Другая дата",  callback_data="back_to_date")
    builder.adjust(1)
    return builder.as_markup()


# ─── АНАЛИТИКА ────────────────────────────────────────────────────────────────

import calendar as _cal_mod
from datetime import date as _date_cls

MONTHS_FULL_RU = {
    1: "Январь",   2: "Февраль",  3: "Март",
    4: "Апрель",   5: "Май",      6: "Июнь",
    7: "Июль",     8: "Август",   9: "Сентябрь",
    10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}
MONTHS_GEN_RU = {
    1: "январь",   2: "февраль",  3: "март",
    4: "апрель",   5: "май",      6: "июнь",
    7: "июль",     8: "август",   9: "сентябрь",
    10: "октябрь", 11: "ноябрь", 12: "декабрь",
}


def calc_month_weeks(
    year: int, month: int, today: _date_cls
) -> list[tuple[_date_cls, _date_cls]]:
    """Calendar Mon–Sun weeks within the month, clamped to month boundaries.
    Only returns weeks where the clamped week-start <= today."""
    _, last_day = _cal_mod.monthrange(year, month)
    m_start = _date_cls(year, month, 1)
    m_end   = _date_cls(year, month, last_day)
    first_monday = m_start - timedelta(days=m_start.weekday())
    weeks: list[tuple[_date_cls, _date_cls]] = []
    cur = first_monday
    while cur <= m_end:
        ws = max(cur, m_start)
        we = min(cur + timedelta(days=6), m_end)
        if ws <= today:
            weeks.append((ws, we))
        cur += timedelta(days=7)
    return weeks


def analytics_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 По месяцам",    callback_data="an:months")
    builder.button(text="📆 Задать период", callback_data="an:custom")
    builder.adjust(2)
    return builder.as_markup()


def analytics_months_kb(months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for year, month in reversed(months):
        builder.button(
            text=f"{MONTHS_FULL_RU[month]} {year}",
            callback_data=f"an:month:{year}:{month}",
        )
    builder.button(text="◀️ Назад", callback_data="an:back")
    n = len(months)
    layout = [2] * (n // 2) + ([1] if n % 2 else []) + [1]
    builder.adjust(*layout)
    return builder.as_markup()


def analytics_weeks_kb(
    year: int, month: int, weeks: list[tuple[_date_cls, _date_cls]]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ws, we in weeks:
        builder.button(
            text=f"{ws.strftime('%d.%m')} — {we.strftime('%d.%m')}",
            callback_data=f"an:week:{ws.strftime('%Y%m%d')}:{we.strftime('%Y%m%d')}",
        )
    _, last = _cal_mod.monthrange(year, month)
    m_start = _date_cls(year, month, 1)
    m_end   = _date_cls(year, month, last)
    builder.button(
        text=f"📅 За весь {MONTHS_GEN_RU[month]}",
        callback_data=f"an:week:{m_start.strftime('%Y%m%d')}:{m_end.strftime('%Y%m%d')}",
    )
    builder.button(text="◀️ К месяцам", callback_data="an:months")
    n = len(weeks)
    layout = [2] * (n // 2) + ([1] if n % 2 else []) + [1, 1]
    builder.adjust(*layout)
    return builder.as_markup()


def analytics_calendar_kb(
    year: int,
    month: int,
    phase: str,
    start: _date_cls | None,
    today: _date_cls,
) -> InlineKeyboardMarkup:
    """Inline calendar grid. phase='start'|'end'. start=already-picked start date."""
    builder = InlineKeyboardBuilder()
    # ── Navigation ─────────────────────────────────────────────────────────
    py, pm = (year - 1, 12) if month == 1  else (year, month - 1)
    ny, nm = (year + 1, 1)  if month == 12 else (year, month + 1)
    builder.button(text="◀️",                              callback_data=f"acal:nav:{py}:{pm}")
    builder.button(text=f"{MONTHS_FULL_RU[month]} {year}", callback_data="acal:no")
    builder.button(text="▶️",                              callback_data=f"acal:nav:{ny}:{nm}")
    # ── Weekday headers ─────────────────────────────────────────────────────
    for wd in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"):
        builder.button(text=wd, callback_data="acal:no")
    # ── Day grid ────────────────────────────────────────────────────────────
    cal_weeks = _cal_mod.monthcalendar(year, month)
    for week in cal_weeks:
        for day_num in week:
            if day_num == 0:
                builder.button(text=" ", callback_data="acal:no")
                continue
            d = _date_cls(year, month, day_num)
            if d == start and phase == "end":
                text, cb = f"✅{day_num}", f"acal:d:{d.strftime('%Y%m%d')}"
            elif d > today:
                text, cb = "·", "acal:no"
            elif phase == "end" and start and d < start:
                text, cb = "·", "acal:no"
            else:
                text, cb = str(day_num), f"acal:d:{d.strftime('%Y%m%d')}"
            builder.button(text=text, callback_data=cb)
    # ── Cancel ──────────────────────────────────────────────────────────────
    builder.button(text="❌ Отмена", callback_data="acal:cancel")
    builder.adjust(3, 7, *([7] * len(cal_weeks)), 1)
    return builder.as_markup()
