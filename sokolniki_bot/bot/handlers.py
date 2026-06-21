import logging
import os

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, Contact, FSInputFile, LinkPreviewOptions, Message,
)
from sqlalchemy import select

from bot.keyboards import (
    cancel_kb, content_type_kb, dates_kb, free_episode_kb, hours_kb,
    main_menu, phone_request_kb, prices_kb, remove_kb, times_kb,
)
from bot.states import BookingForm
from config import ADMIN_ID
from database.db import (
    async_session, create_booking, get_booked_hours,
    get_content, get_or_create_client, update_client_profile,
)
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


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
    section_key = "booking" if lead_type == "booking" else "free"
    await send_section(msg, section_key)
    await msg.answer("👤 <b>Как вас зовут?</b>",
                     parse_mode="HTML", reply_markup=cancel_kb(),
                     link_preview_options=NO_PREVIEW)


@router.message(F.text.in_({"🏠 Забронировать студию", "🎬 Записать подкаст"}))
async def booking_start_msg(message: Message, state: FSMContext) -> None:
    await _start_booking(message, state, lead_type="booking")


@router.callback_query(F.data == "go_booking")
async def booking_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_booking(callback.message, state, lead_type="booking")


# ─── FREE EPISODE ─────────────────────────────────────────────────────────────

@router.message(F.text == "🔥 Первый выпуск бесплатно")
async def show_free_episode(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_section(message, "free", reply_markup=free_episode_kb())


@router.callback_query(F.data == "go_free_episode")
async def start_free_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_booking(callback.message, state, lead_type="free_episode")


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
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n🕐 <b>Выберите время начала:</b>",
        parse_mode="HTML", reply_markup=times_kb(blocked))
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


@router.callback_query(BookingForm.hours, F.data.startswith("bhours:"))
async def booking_hours(callback: CallbackQuery, state: FSMContext) -> None:
    hours = callback.data.split(":", 1)[1]
    await state.update_data(hours=int(hours))
    await state.set_state(BookingForm.phone)
    # Switch to Reply keyboard for native phone sharing
    await callback.message.answer(
        f"✅ {hours} ч\n\n📱 <b>Укажите ваш номер телефона:</b>\n"
        "└ Нажмите кнопку ниже или введите вручную",
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
            "⚠️ Номер не распознан. Введите в формате <b>+7 999 123-45-67</b> "
            "или нажмите кнопку «📱 Поделиться номером».",
            parse_mode="HTML")
        return
    await _finish_booking(message, state, phone)


async def _finish_booking(message: Message, state: FSMContext, phone: str) -> None:
    data = await state.get_data()
    await state.clear()

    tg_id     = message.from_user.id
    username  = message.from_user.username
    lead_type = data.get("lead_type", "booking")
    hours_int = data.get("hours", 1)

    # Upsert client profile
    client = await get_or_create_client(tg_id, username)
    client = await update_client_profile(tg_id, data.get("name", ""), phone)

    # Create a new Booking record (not overwrite)
    booking = await create_booking(client.id, {
        "lead_type":    lead_type,
        "content_type": data.get("content_type"),
        "date":         data.get("date"),
        "time":         data.get("time"),
        "hours":        hours_int,
    })

    icon = "🔥" if lead_type == "free_episode" else "📋"
    tag  = "Бесплатный выпуск" if lead_type == "free_episode" else "Бронирование"

    summary = (
        f"{icon} <b>Ваша заявка принята!</b>\n\n"
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
        f"{'🔥' if lead_type == 'free_episode' else '🆕'} <b>Новая заявка — {tag}</b>\n"
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
