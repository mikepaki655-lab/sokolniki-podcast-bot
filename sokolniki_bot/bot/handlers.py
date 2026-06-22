import logging
import os
from datetime import date, datetime, timezone, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, Contact, FSInputFile, LinkPreviewOptions, Message,
)
from sqlalchemy import select

from bot.keyboards import (
    cancel_kb, confirm_client_cancel_kb, content_type_kb, dates_kb, hours_kb,
    main_menu, my_bookings_menu_kb, my_booking_done_item_kb, my_booking_item_kb,
    phone_request_kb, prices_kb, remove_kb, reschedule_confirm_kb, reschedule_dates_kb,
    reschedule_hours_kb, reschedule_slot_conflict_kb, reschedule_times_kb,
    skip_reason_kb, slot_conflict_kb, times_kb,
)
from bot.states import BookingForm, ClientRescheduleState, MyBookingsState
from config import ADMIN_ID
from database.db import (
    async_session, cancel_booking, create_booking, get_booked_hours,
    get_client_bookings, get_booking_with_client, get_max_available_hours,
    get_content, get_or_create_client, reschedule_client_booking,
)
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

MOSCOW_TZ = timezone(timedelta(hours=3))

# Status labels shown to the client in "Мои брони"
CLIENT_STATUS_LABELS = {
    "new_request":      "⏳ Ждёт подтверждения от администратора",
    "lead":             "⏳ Ждёт подтверждения от администратора",
    "confirmed":        "✅ Подтверждена",
    "recorded":         "🎙 Ждём вас в студии",
    "paid":             "🎙 Ждём вас в студии",
    "done_no_pay":      "🔄 Услуга оказана, в ожидании оплаты",
    "rescheduled_done": "🔄 Перенесена — ждём подтверждения",
    "done_paid":        "✅ Завершена",
}

# Active statuses shown in "Активные" (everything except done_paid)
ACTIVE_STATUSES = {"new_request", "lead", "confirmed", "recorded", "paid",
                   "done_no_pay", "rescheduled_done"}
# Only done_paid goes to "Завершённые"
DONE_CLIENT_STATUSES = {"done_paid"}


# ─── UTILS ────────────────────────────────────────────────────────────────────

async def send_section(message: Message, key: str, reply_markup=None) -> None:
    section = await get_content(key)
    if not section:
        return
    photo_sent = False
    if section.photo_file_id:
        try:
            await message.answer_photo(
                photo=section.photo_file_id, caption=section.text,
                parse_mode="HTML", reply_markup=reply_markup,
            )
            photo_sent = True
        except Exception:
            pass
    if not photo_sent and section.local_banner:
        path = os.path.join(IMAGES_DIR, section.local_banner)
        if os.path.exists(path):
            await message.answer_photo(
                photo=FSInputFile(path), caption=section.text,
                parse_mode="HTML", reply_markup=reply_markup,
            )
            photo_sent = True
    if not photo_sent:
        await message.answer(section.text, parse_mode="HTML",
                             reply_markup=reply_markup, link_preview_options=NO_PREVIEW)


def _validate_phone(text: str) -> str | None:
    """Returns cleaned phone string or None if invalid."""
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) < 10:
        return None
    return text.strip()


def _today_min_hour() -> int:
    """Minimum bookable hour for today (Moscow time).
    Formula: current_hour + 2 if minutes > 0, else current_hour + 1.
    Example: 12:16 → min_hour=14; 14:00 → min_hour=15.
    """
    now = datetime.now(MOSCOW_TZ)
    return now.hour + (2 if now.minute > 0 else 1)


def _is_today(date_str: str) -> bool:
    """Check if DD.MM.YYYY string equals today (Moscow)."""
    try:
        return date_str == datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    except Exception:
        return False


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await get_or_create_client(message.from_user.id, message.from_user.username)
    await send_section(message, "welcome", reply_markup=main_menu())


# ─── /cancel ──────────────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("❌ Действие отменено. Выберите раздел 👇",
                             reply_markup=main_menu(), link_preview_options=NO_PREVIEW)
    else:
        await message.answer("Выберите раздел 👇",
                             reply_markup=main_menu(), link_preview_options=NO_PREVIEW)


# ─── BOOKING FLOW ─────────────────────────────────────────────────────────────

async def _start_booking(msg: Message, state: FSMContext, lead_type: str = "booking") -> None:
    await state.clear()
    await state.update_data(lead_type=lead_type)
    await state.set_state(BookingForm.name)

    caption = "🎙 <b>Студия «Сокольники»</b>\n\n👤 Как вас зовут?"
    section = await get_content("booking")
    photo_sent = False
    if section:
        if section.photo_file_id:
            try:
                await msg.answer_photo(section.photo_file_id, caption=caption, parse_mode="HTML")
                photo_sent = True
            except Exception:
                pass
        if not photo_sent and section.local_banner:
            path = os.path.join(IMAGES_DIR, section.local_banner)
            if os.path.exists(path):
                await msg.answer_photo(FSInputFile(path), caption=caption, parse_mode="HTML")
                photo_sent = True
    if not photo_sent:
        await msg.answer(caption, parse_mode="HTML", link_preview_options=NO_PREVIEW)


@router.message(F.text.in_({"🏠 Забронировать студию", "🎬 Записать подкаст"}))
async def booking_start_msg(message: Message, state: FSMContext) -> None:
    await _start_booking(message, state, lead_type="booking")


@router.callback_query(F.data == "go_booking")
async def booking_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_booking(callback.message, state, lead_type="booking")



# ─── SHARED BOOKING STEPS ─────────────────────────────────────────────────────

@router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if len(name) < 2:
        await message.answer("⚠️ Введите имя (минимум 2 символа).")
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.content_type)
    await message.answer("🎬 <b>Какой контент хотите снимать?</b>",
                         parse_mode="HTML", reply_markup=content_type_kb(),
                         link_preview_options=NO_PREVIEW)


@router.callback_query(BookingForm.content_type, F.data.startswith("ctype:"))
async def booking_content_type(callback: CallbackQuery, state: FSMContext) -> None:
    content = callback.data.split(":", 1)[1]
    await state.update_data(content_type=content)
    await state.set_state(BookingForm.date)
    await callback.message.edit_text(
        f"✅ {content}\n\n📅 <b>Выберите желаемую дату:</b>",
        parse_mode="HTML", reply_markup=dates_kb())
    await callback.answer()


@router.callback_query(BookingForm.date, F.data.startswith("bdate:"))
async def booking_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await state.update_data(date=chosen_date)
    await state.set_state(BookingForm.time)
    blocked = await get_booked_hours(chosen_date)
    min_hour = _today_min_hour() if _is_today(chosen_date) else 0
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n🕐 <b>Выберите время начала:</b>",
        parse_mode="HTML", reply_markup=times_kb(blocked, min_hour=min_hour))
    await callback.answer()


@router.callback_query(BookingForm.time, F.data == "no_slots")
async def booking_no_slots(callback: CallbackQuery) -> None:
    await callback.answer("На эту дату нет свободных слотов. Выберите другую.", show_alert=True)


@router.callback_query(BookingForm.time, F.data.startswith("btime:"))
async def booking_time(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_time = callback.data.split("btime:", 1)[1]
    await state.update_data(time=chosen_time)
    await state.set_state(BookingForm.hours)
    await callback.message.edit_text(
        f"✅ {chosen_time}\n\n⏱ <b>Сколько часов нужна студия?</b>",
        parse_mode="HTML", reply_markup=hours_kb())
    await callback.answer()


@router.callback_query(BookingForm.hours, F.data == "back_to_time")
async def conflict_back_to_time(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(BookingForm.time)
    chosen_date = data.get("date", "")
    blocked = await get_booked_hours(chosen_date)
    min_hour = _today_min_hour() if _is_today(chosen_date) else 0
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n🕐 <b>Выберите время начала:</b>",
        parse_mode="HTML", reply_markup=times_kb(blocked, min_hour=min_hour),
    )
    await callback.answer()


@router.callback_query(BookingForm.hours, F.data == "back_to_date")
async def conflict_back_to_date(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(BookingForm.date)
    await callback.message.edit_text(
        f"✅ {data.get('content_type', '')}\n\n📅 <b>Выберите желаемую дату:</b>",
        parse_mode="HTML", reply_markup=dates_kb(),
    )
    await callback.answer()


@router.callback_query(BookingForm.hours, F.data.startswith("bhours:"))
async def booking_hours(callback: CallbackQuery, state: FSMContext) -> None:
    hours = int(callback.data.split(":", 1)[1])
    data  = await state.get_data()
    chosen_date = data.get("date", "")
    chosen_time = data.get("time", "")

    # Check if the chosen slot fits without overlapping existing bookings
    if chosen_date and chosen_time:
        start_hour = int(chosen_time.split(":")[0])
        available  = await get_max_available_hours(chosen_date, start_hour, hours)
        if available < hours:
            if available == 0:
                msg_text = (
                    f"⚠️ Время <b>{chosen_time}</b> на <b>{chosen_date}</b> уже занято.\n\n"
                    "Пожалуйста, выберите другое время или дату 👇"
                )
            else:
                noun = "час" if available == 1 else "часа" if available < 5 else "часов"
                msg_text = (
                    f"⚠️ На <b>{chosen_date}</b> в <b>{chosen_time}</b> бронь возможна "
                    f"только на <b>{available} {noun}</b> — дальше студия занята.\n\n"
                    "Выберите другое время / дату или возьмите доступное время 👇"
                )
            await callback.message.edit_text(msg_text, parse_mode="HTML",
                                             reply_markup=slot_conflict_kb(available))
            await callback.answer()
            return

    await state.update_data(hours=hours)
    await state.set_state(BookingForm.phone)
    await callback.message.answer(
        f"✅ {hours} ч\n\n📱 <b>Укажите ваш номер телефона:</b>\n"
        "└ Введите номер в формате <code>+7ХХХХХХХХХХ</code>",
        parse_mode="HTML",
        reply_markup=phone_request_kb(),
        link_preview_options=NO_PREVIEW,
    )
    await callback.answer()


# Phone via native Telegram contact button
@router.message(BookingForm.phone, F.contact)
async def booking_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await _finish_booking(message, state, phone)


# Phone via manual text input
@router.message(BookingForm.phone, F.text)
async def booking_phone_text(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=main_menu(),
                             link_preview_options=NO_PREVIEW)
        return
    phone = _validate_phone(message.text)
    if not phone:
        await message.answer(
            "⚠️ Неверный формат. Введите номер в формате <code>+7ХХХХХХХХХХ</code>",
            parse_mode="HTML",
            reply_markup=remove_kb(),
        )
        return
    await _finish_booking(message, state, phone)


async def _finish_booking(message: Message, state: FSMContext, phone: str) -> None:
    data = await state.get_data()
    await state.clear()

    tg_id     = message.from_user.id
    username  = message.from_user.username
    lead_type = data.get("lead_type", "booking")
    hours_int = data.get("hours", 1)

    # Ensure client record exists (tracks Telegram identity only)
    client = await get_or_create_client(tg_id, username)

    # Create booking with the name/phone entered THIS time — never overwrites other bookings
    booking = await create_booking(client.id, {
        "name":         data.get("name", ""),
        "phone":        phone,
        "lead_type":    lead_type,
        "content_type": data.get("content_type"),
        "date":         data.get("date"),
        "time":         data.get("time"),
        "hours":        hours_int,
    })

    summary = (
        "📋 <b>Ваша заявка принята!</b>\n\n"
        f"├ 👤 Имя: <b>{data.get('name')}</b>\n"
        f"├ 📱 Телефон: <b>{phone}</b>\n"
        f"├ 🎬 Контент: <b>{data.get('content_type')}</b>\n"
        f"├ 📅 Дата: <b>{data.get('date')}</b>\n"
        f"├ 🕐 Время: <b>{data.get('time')}</b>\n"
        f"└ ⏱ Длительность: <b>{hours_int} ч</b>\n\n"
        "✅ Мы свяжемся с вами в ближайшее время\n"
        "└ для подтверждения брони 🎙"
    )
    await message.answer(summary, parse_mode="HTML",
                         reply_markup=main_menu(), link_preview_options=NO_PREVIEW)

    admin_text = (
        f"🆕 <b>Новая заявка — Бронирование</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 📱 {phone}\n"
        f"├ 🎬 {data.get('content_type')}\n"
        f"├ 📅 {data.get('date')} в {data.get('time')}\n"
        f"├ ⏱ {hours_int} ч\n"
        f"├ 🪪 @{username or '—'} · <code>{tg_id}</code>\n"
        f"└ #заявка_{booking.id}"
    )
    try:
        await message.bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML",
                                       link_preview_options=NO_PREVIEW)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


# ─── МОИ БРОНИ ────────────────────────────────────────────────────────────────

@router.message(F.text == "📅 Мои брони")
async def my_bookings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "📅 <b>Мои брони</b>\n└ Выберите раздел:",
        parse_mode="HTML",
        reply_markup=my_bookings_menu_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(F.data == "my_bookings:active")
async def my_bookings_active(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    bookings = await get_client_bookings(callback.from_user.id)
    active = [b for b in bookings if b.status in ACTIVE_STATUSES]

    if not active:
        await callback.message.edit_text(
            "📋 <b>Активные брони</b>\n\n└ У вас нет активных броней.",
            parse_mode="HTML",
            reply_markup=my_bookings_menu_kb(),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for b in active:
        status_label = CLIENT_STATUS_LABELS.get(b.status, b.status)
        date_part = f" {b.booking_date}" if b.booking_date else ""
        label = f"#{b.id}{date_part} · {status_label}"
        builder.button(text=label[:60], callback_data=f"my_booking_detail:{b.id}")
    builder.button(text="◀️ Назад", callback_data="my_bookings:menu")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📋 <b>Активные брони</b> ({len(active)})\n└ Выберите для подробностей:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "my_bookings:done")
async def my_bookings_done(callback: CallbackQuery) -> None:
    bookings = await get_client_bookings(callback.from_user.id)
    done = [b for b in bookings if b.status in DONE_CLIENT_STATUSES]

    if not done:
        await callback.message.edit_text(
            "✅ <b>Завершённые брони</b>\n\n└ Завершённых броней пока нет.",
            parse_mode="HTML",
            reply_markup=my_bookings_menu_kb(),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for b in done:
        date_part = f" {b.booking_date}" if b.booking_date else ""
        amount_part = f" · {int(b.payment_amount):,} ₽" if b.payment_amount else ""
        label = f"#{b.id}{date_part}{amount_part}"
        builder.button(text=label[:60], callback_data=f"my_booking_done_detail:{b.id}")
    builder.button(text="◀️ Назад", callback_data="my_bookings:menu")
    builder.adjust(1)

    await callback.message.edit_text(
        f"✅ <b>Завершённые брони</b> ({len(done)})\n└ Выберите для подробностей:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "my_bookings:menu")
async def my_bookings_menu_cb(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📅 <b>Мои брони</b>\n└ Выберите раздел:",
        parse_mode="HTML",
        reply_markup=my_bookings_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("my_booking_detail:"))
async def my_booking_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    booking_id = int(callback.data.split(":")[1])
    pair = await get_booking_with_client(booking_id)
    if not pair:
        await callback.answer("Бронь не найдена.", show_alert=True)
        return
    booking, client = pair

    # Security: only the booking owner can view
    if client.telegram_id != callback.from_user.id:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    status_label = CLIENT_STATUS_LABELS.get(booking.status, booking.status)
    hours_str = f"{int(booking.booking_hours)} ч" if booking.booking_hours else "—"

    # Compute end time if possible
    time_range = booking.booking_time or "—"
    if booking.booking_time and booking.booking_hours:
        try:
            sh = int(booking.booking_time.split(":")[0])
            eh = sh + booking.booking_hours
            time_range = f"{sh:02d}:00 – {eh:02d}:00"
        except Exception:
            pass

    text = (
        f"📋 <b>Бронь #{booking.id}</b>\n\n"
        f"├ 🎬 Контент: {booking.content_type or '—'}\n"
        f"├ 📅 Дата: {booking.booking_date or '—'}\n"
        f"├ 🕐 Время: {time_range}\n"
        f"├ ⏱ Длительность: {hours_str}\n"
        f"└ 📊 Статус: {status_label}"
    )

    can_cancel = booking.status in {"new_request", "lead", "confirmed",
                                    "recorded", "paid", "rescheduled_done"}
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=my_booking_item_kb(
            booking.id,
            can_cancel=can_cancel,
            can_reschedule=can_cancel,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("my_booking_done_detail:"))
async def my_booking_done_detail(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[1])
    pair = await get_booking_with_client(booking_id)
    if not pair:
        await callback.answer("Бронь не найдена.", show_alert=True)
        return
    booking, client = pair

    if client.telegram_id != callback.from_user.id:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    hours_str = f"{int(booking.booking_hours)} ч" if booking.booking_hours else "—"
    amount_str = f"{int(booking.payment_amount):,} ₽" if booking.payment_amount else "—"

    time_range = booking.booking_time or "—"
    if booking.booking_time and booking.booking_hours:
        try:
            sh = int(booking.booking_time.split(":")[0])
            eh = sh + booking.booking_hours
            time_range = f"{sh:02d}:00 – {eh:02d}:00"
        except Exception:
            pass

    text = (
        f"✅ <b>Завершённая бронь #{booking.id}</b>\n\n"
        f"├ 🎬 Контент: {booking.content_type or '—'}\n"
        f"├ 📅 Дата: {booking.booking_date or '—'}\n"
        f"├ 🕐 Время: {time_range}\n"
        f"├ ⏱ Длительность: {hours_str}\n"
        f"└ 💰 Оплата: {amount_str}"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=my_booking_done_item_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_ask(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        f"❓ <b>Вы уверены, что хотите отменить бронь #{booking_id}?</b>\n\n"
        "После отмены слот освободится для других гостей.",
        parse_mode="HTML",
        reply_markup=confirm_client_cancel_kb(booking_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking_yes:"))
async def cancel_booking_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.split(":")[1])

    # Verify ownership
    pair = await get_booking_with_client(booking_id)
    if not pair or pair[1].telegram_id != callback.from_user.id:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    # Cancel the booking
    await cancel_booking(booking_id)

    # Store booking_id for admin notification after reason is collected
    await state.update_data(cancelled_booking_id=booking_id,
                            cancelled_booking_date=pair[0].booking_date or "—",
                            cancelled_booking_time=pair[0].booking_time or "—",
                            cancelled_client_name=pair[0].guest_name or pair[1].name or "—",
                            cancelled_client_phone=pair[0].guest_phone or pair[1].phone or "—")
    await state.set_state(MyBookingsState.cancel_reason)

    await callback.message.edit_text(
        "😔 <b>Нам жаль, что вы отменили бронирование.</b>\n\n"
        "Надеемся, вы вскоре снова вернётесь к нам! 🎙\n\n"
        "Если есть причина, которую вы хотите нам сообщить,\n"
        "напишите её в сообщении ниже.\n"
        "Или нажмите «Пропустить».",
        parse_mode="HTML",
        reply_markup=skip_reason_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_reason_skip")
async def cancel_reason_skip(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await _send_cancel_admin_notify(callback.bot, data, reason=None,
                                   username=callback.from_user.username,
                                   tg_id=callback.from_user.id)
    await callback.message.edit_text(
        "✅ <b>Бронирование отменено.</b>\n\n"
        "Ждём вас снова в студии «Сокольники»! 🎙",
        parse_mode="HTML",
    )
    await callback.answer()
    await callback.message.answer("Выберите раздел 👇",
                                  reply_markup=main_menu(), link_preview_options=NO_PREVIEW)


@router.message(MyBookingsState.cancel_reason)
async def cancel_reason_text(message: Message, state: FSMContext) -> None:
    reason = message.text.strip() if message.text else ""
    data = await state.get_data()
    await state.clear()
    await _send_cancel_admin_notify(message.bot, data, reason=reason or None,
                                   username=message.from_user.username,
                                   tg_id=message.from_user.id)
    await message.answer(
        "✅ <b>Спасибо за сообщение!</b>\n\nОтветим вам в ближайшее время. 📩",
        parse_mode="HTML",
        reply_markup=main_menu(),
        link_preview_options=NO_PREVIEW,
    )


async def _send_cancel_admin_notify(bot, data: dict, reason: str | None,
                                    username: str | None, tg_id: int) -> None:
    booking_id = data.get("cancelled_booking_id", "?")
    bdate      = data.get("cancelled_booking_date", "—")
    btime      = data.get("cancelled_booking_time", "—")
    cname      = data.get("cancelled_client_name", "—")
    cphone     = data.get("cancelled_client_phone", "—")
    tg         = f"@{username}" if username else f"<code>{tg_id}</code>"
    reason_line = f"\n└ 💬 Причина: {reason}" if reason else "\n└ 💬 Причина: не указана"

    text = (
        f"❌ <b>Клиент отменил бронирование #{booking_id}</b>\n\n"
        f"├ 👤 {cname} ({tg})\n"
        f"├ 📱 {cphone}\n"
        f"├ 📅 Дата: {bdate} в {btime}"
        f"{reason_line}"
    )
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML",
                               link_preview_options=NO_PREVIEW)
    except Exception as e:
        logger.error(f"Admin cancel notify failed: {e}")


# ─── КЛИЕНТСКИЙ ПЕРЕНОС БРОНИ ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reschedule_booking:"))
async def client_reschedule_start(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.split(":")[1])
    pair = await get_booking_with_client(booking_id)
    if not pair or pair[1].telegram_id != callback.from_user.id:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    booking = pair[0]
    await state.update_data(rs_booking_id=booking_id,
                            rs_old_date=booking.booking_date or "—",
                            rs_old_time=booking.booking_time or "—")
    await state.set_state(ClientRescheduleState.date)
    await callback.message.edit_text(
        "📅 <b>Перенос брони</b>\n\n"
        "Выберите <b>новую дату</b>:",
        parse_mode="HTML",
        reply_markup=reschedule_dates_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rs_date:"), ClientRescheduleState.date)
async def client_reschedule_date(callback: CallbackQuery, state: FSMContext) -> None:
    new_date = callback.data.split(":", 1)[1]
    data = await state.get_data()
    booking_id = data["rs_booking_id"]

    # Compute min_hour if today
    today_str = date.today().strftime("%d.%m.%Y")
    min_hour = 0
    if new_date == today_str:
        now_msk = datetime.now(MOSCOW_TZ)
        min_hour = now_msk.hour + (2 if now_msk.minute > 0 else 1)

    # Blocked hours, excluding this booking's own slot
    blocked = await get_booked_hours(new_date, exclude_booking_id=booking_id)

    await state.update_data(rs_new_date=new_date, rs_min_hour=min_hour)
    await state.set_state(ClientRescheduleState.time)

    await callback.message.edit_text(
        f"📅 <b>Перенос брони</b>\n"
        f"└ Новая дата: <b>{new_date}</b>\n\n"
        "Выберите <b>время начала</b>:",
        parse_mode="HTML",
        reply_markup=reschedule_times_kb(blocked=blocked, min_hour=min_hour),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rs_time:"), ClientRescheduleState.time)
async def client_reschedule_time(callback: CallbackQuery, state: FSMContext) -> None:
    new_time = callback.data.split(":", 1)[1]
    start_hour = int(new_time.split(":")[0])
    data = await state.get_data()
    booking_id = data["rs_booking_id"]
    new_date   = data["rs_new_date"]

    # Check max available hours excluding current booking
    max_avail = await get_max_available_hours(
        new_date, start_hour, 12,
        exclude_booking_id=booking_id,
    )

    await state.update_data(rs_new_time=new_time, rs_start_hour=start_hour)
    await state.set_state(ClientRescheduleState.hours)

    if max_avail == 0:
        await callback.message.edit_text(
            f"📅 <b>Перенос брони</b>\n"
            f"├ Дата: <b>{new_date}</b>\n"
            f"└ Время: <b>{new_time}</b>\n\n"
            "⛔ <b>На это время нет свободных слотов.</b>\n"
            "Выберите другое время или дату.",
            parse_mode="HTML",
            reply_markup=reschedule_slot_conflict_kb(0),
        )
    elif max_avail < 12:
        await callback.message.edit_text(
            f"📅 <b>Перенос брони</b>\n"
            f"├ Дата: <b>{new_date}</b>\n"
            f"└ Время: <b>{new_time}</b>\n\n"
            f"⚠️ На это время доступно не более <b>{max_avail} ч</b> "
            "(следующий гость приходит раньше).\n\n"
            "Выберите длительность:",
            parse_mode="HTML",
            reply_markup=reschedule_slot_conflict_kb(max_avail),
        )
    else:
        await callback.message.edit_text(
            f"📅 <b>Перенос брони</b>\n"
            f"├ Дата: <b>{new_date}</b>\n"
            f"└ Время: <b>{new_time}</b>\n\n"
            "Выберите <b>длительность</b>:",
            parse_mode="HTML",
            reply_markup=reschedule_hours_kb(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("rs_hours:"), ClientRescheduleState.hours)
async def client_reschedule_hours(callback: CallbackQuery, state: FSMContext) -> None:
    new_hours = int(callback.data.split(":")[1])
    data = await state.get_data()
    booking_id = data["rs_booking_id"]
    new_date   = data["rs_new_date"]
    new_time   = data["rs_new_time"]
    start_hour = data["rs_start_hour"]

    # Final availability check
    max_avail = await get_max_available_hours(
        new_date, start_hour, new_hours,
        exclude_booking_id=booking_id,
    )
    if max_avail < new_hours:
        await callback.answer(
            f"⚠️ Конфликт слотов. Доступно не более {max_avail} ч.",
            show_alert=True,
        )
        return

    end_h = start_hour + new_hours
    await state.update_data(rs_new_hours=new_hours)
    await state.set_state(ClientRescheduleState.confirm)

    await callback.message.edit_text(
        f"📅 <b>Подтверждение переноса</b>\n\n"
        f"├ 📅 Новая дата: <b>{new_date}</b>\n"
        f"├ 🕐 Время: <b>{start_hour:02d}:00 – {end_h:02d}:00</b>\n"
        f"└ ⏱ Длительность: <b>{new_hours} ч</b>\n\n"
        "Подтвердить перенос?",
        parse_mode="HTML",
        reply_markup=reschedule_confirm_kb(booking_id),
    )
    await callback.answer()


@router.callback_query(F.data == "rs_back_to_time")
async def rs_back_to_time(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    booking_id = data.get("rs_booking_id")
    new_date   = data.get("rs_new_date", "")
    min_hour   = data.get("rs_min_hour", 0)
    blocked = await get_booked_hours(new_date, exclude_booking_id=booking_id)
    await state.set_state(ClientRescheduleState.time)
    await callback.message.edit_text(
        f"📅 <b>Перенос брони</b>\n"
        f"└ Новая дата: <b>{new_date}</b>\n\n"
        "Выберите <b>другое время</b>:",
        parse_mode="HTML",
        reply_markup=reschedule_times_kb(blocked=blocked, min_hour=min_hour),
    )
    await callback.answer()


@router.callback_query(F.data == "rs_back_to_date")
async def rs_back_to_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientRescheduleState.date)
    await callback.message.edit_text(
        "📅 <b>Перенос брони</b>\n\n"
        "Выберите <b>другую дату</b>:",
        parse_mode="HTML",
        reply_markup=reschedule_dates_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reschedule_confirm_yes:"))
async def client_reschedule_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.split(":")[1])
    pair = await get_booking_with_client(booking_id)
    if not pair or pair[1].telegram_id != callback.from_user.id:
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    new_date  = data.get("rs_new_date", "")
    new_time  = data.get("rs_new_time", "")
    new_hours = int(data.get("rs_new_hours", 1))
    old_date  = data.get("rs_old_date", "—")
    old_time  = data.get("rs_old_time", "—")
    await state.clear()

    await reschedule_client_booking(booking_id, new_date, new_time, new_hours)

    start_h = int(new_time.split(":")[0])
    end_h   = start_h + new_hours

    await callback.message.edit_text(
        f"✅ <b>Перенос подтверждён!</b>\n\n"
        f"├ 📅 Новая дата: <b>{new_date}</b>\n"
        f"├ 🕐 Время: <b>{start_h:02d}:00 – {end_h:02d}:00</b>\n"
        f"└ ⏱ Длительность: <b>{new_hours} ч</b>\n\n"
        "Ждём вас в студии «Сокольники»! 🎙",
        parse_mode="HTML",
    )

    # Notify admin
    booking, client = pair
    tg = f"@{client.username}" if client.username else f"<code>{client.telegram_id}</code>"
    try:
        await callback.bot.send_message(
            ADMIN_ID,
            f"🔄 <b>Клиент перенёс бронь #{booking_id}</b>\n\n"
            f"├ 👤 {booking.guest_name or client.name or '—'} ({tg})\n"
            f"├ 📅 Было: <b>{old_date} в {old_time}</b>\n"
            f"└ 📅 Стало: <b>{new_date} в {new_time}</b> · {new_hours} ч",
            parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )
    except Exception as e:
        logger.error(f"Admin reschedule notify failed: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("reschedule_confirm_no:"))
async def client_reschedule_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    booking_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        "❌ Перенос отменён.",
        parse_mode="HTML",
    )
    await callback.answer()
    # Return to booking detail
    await callback.message.answer(
        "Открываю карточку брони...",
        link_preview_options=NO_PREVIEW,
    )
    # Simulate re-open by posting a new detail message
    pair = await get_booking_with_client(booking_id)
    if pair:
        booking, _ = pair
        status_label = CLIENT_STATUS_LABELS.get(booking.status, booking.status)
        hours_str = f"{int(booking.booking_hours)} ч" if booking.booking_hours else "—"
        time_range = booking.booking_time or "—"
        if booking.booking_time and booking.booking_hours:
            try:
                sh = int(booking.booking_time.split(":")[0])
                eh = sh + booking.booking_hours
                time_range = f"{sh:02d}:00 – {eh:02d}:00"
            except Exception:
                pass
        text = (
            f"📋 <b>Бронь #{booking.id}</b>\n\n"
            f"├ 🎬 Контент: {booking.content_type or '—'}\n"
            f"├ 📅 Дата: {booking.booking_date or '—'}\n"
            f"├ 🕐 Время: {time_range}\n"
            f"├ ⏱ Длительность: {hours_str}\n"
            f"└ 📊 Статус: {status_label}"
        )
        can_act = booking.status in {"new_request", "lead", "confirmed",
                                     "recorded", "paid", "rescheduled_done"}
        await callback.message.answer(
            text, parse_mode="HTML",
            reply_markup=my_booking_item_kb(booking.id, can_cancel=can_act, can_reschedule=can_act),
        )


# ─── PRICES ───────────────────────────────────────────────────────────────────

@router.message(F.text == "💰 Узнать цены")
async def show_prices(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_section(message, "prices", reply_markup=prices_kb())


# ─── ADDRESS ──────────────────────────────────────────────────────────────────

@router.message(F.text == "📍 Адрес студии")
async def show_address(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_section(message, "address", reply_markup=main_menu())


# ─── CANCEL INLINE ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("❌ Действие отменено")
    except Exception:
        pass
    await callback.message.answer("Выберите раздел меню 👇",
                                  reply_markup=main_menu(),
                                  link_preview_options=NO_PREVIEW)
    await callback.answer()


# ─── CATCH-ALL ────────────────────────────────────────────────────────────────

@router.message()
async def fallback_handler(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is not None:
        return  # inside a form — don't interrupt
    await message.answer("Выберите раздел 👇",
                         reply_markup=main_menu(), link_preview_options=NO_PREVIEW)
