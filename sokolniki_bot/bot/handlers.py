import logging
import os
from datetime import datetime, timezone, timedelta

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, LinkPreviewOptions, Message
from sqlalchemy import select

from bot.keyboards import (
    cancel_kb, content_type_kb, dates_kb, free_episode_kb,
    hours_kb, main_menu, prices_kb, skip_cancel_kb, times_kb,
)
from bot.states import BookingForm, FreeEpisodeForm
from config import ADMIN_ID
from database.db import async_session, get_booked_hours, get_content
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images")
MOSCOW_TZ  = timezone(timedelta(hours=3))
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


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


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == message.from_user.id)
        )
        if not result.scalar_one_or_none():
            session.add(Client(telegram_id=message.from_user.id,
                               username=message.from_user.username))
            await session.commit()
    await send_section(message, "welcome", reply_markup=main_menu())


# ─── BOOKING FLOW ─────────────────────────────────────────────────────────────

async def _start_booking(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingForm.name)
    await send_section(msg, "booking")
    await msg.answer("👤 <b>Как вас зовут?</b>",
                     parse_mode="HTML", reply_markup=cancel_kb(),
                     link_preview_options=NO_PREVIEW)


@router.message(F.text == "🎬 Записать подкаст")
async def booking_start_msg(message: Message, state: FSMContext) -> None:
    await _start_booking(message, state)


@router.callback_query(F.data == "go_booking")
async def booking_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_booking(callback.message, state)


@router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
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
        f"✅ {content}\n\n📅 <b>Выберите желаемую дату съёмок:</b>",
        parse_mode="HTML", reply_markup=dates_kb())
    await callback.answer()


@router.callback_query(BookingForm.date, F.data.startswith("bdate:"))
async def booking_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await state.update_data(date=chosen_date)
    await state.set_state(BookingForm.time)
    blocked = await get_booked_hours(chosen_date)
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n🕐 <b>Выберите время начала съёмок:</b>",
        parse_mode="HTML", reply_markup=times_kb(blocked))
    await callback.answer()


@router.callback_query(BookingForm.time, F.data == "no_slots")
async def booking_no_slots(callback: CallbackQuery) -> None:
    await callback.answer("На эту дату нет свободных слотов. Выберите другую дату.", show_alert=True)


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
    await state.update_data(hours=hours)
    await state.set_state(BookingForm.phone)
    await callback.message.edit_text(
        f"✅ {hours} ч\n\n📱 <b>Укажите ваш номер телефона:</b>",
        parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()


@router.message(BookingForm.phone)
async def booking_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.clear()

    tg_id    = message.from_user.id
    username = message.from_user.username
    hours_int = int(data.get("hours", 1))

    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        fields = dict(
            name=data.get("name"), phone=phone,
            service=data.get("content_type"),
            booking_date=data.get("date"),
            booking_time=data.get("time"),
            booking_hours=hours_int,
            status="new_request", lead_type="booking",
        )
        if client:
            for k, v in fields.items():
                setattr(client, k, v)
        else:
            session.add(Client(telegram_id=tg_id, username=username, **fields))
        await session.commit()

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
        "🔥 <b>Новая заявка на съёмку</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 📱 {phone}\n"
        f"├ 🎬 {data.get('content_type')}\n"
        f"├ 📅 {data.get('date')} в {data.get('time')}\n"
        f"├ ⏱ {hours_int} ч\n"
        f"└ 📱 @{username or '—'} · <code>{tg_id}</code>"
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


# ─── FREE EPISODE — same booking mechanics ───────────────────────────────────

async def _start_free(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FreeEpisodeForm.name)
    await send_section(msg, "free")
    await msg.answer("👤 <b>Как вас зовут?</b>",
                     parse_mode="HTML", reply_markup=cancel_kb(),
                     link_preview_options=NO_PREVIEW)


@router.message(F.text == "🔥 Первый выпуск бесплатно")
async def show_free_episode(message: Message, state: FSMContext) -> None:
    await send_section(message, "free", reply_markup=free_episode_kb())


@router.callback_query(F.data == "go_free_episode")
async def start_free_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _start_free(callback.message, state)


@router.message(FreeEpisodeForm.name)
async def free_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Введите имя (минимум 2 символа).")
        return
    await state.update_data(name=name)
    await state.set_state(FreeEpisodeForm.content_type)
    await message.answer("🎬 <b>Какой контент хотите снимать?</b>",
                         parse_mode="HTML", reply_markup=content_type_kb(),
                         link_preview_options=NO_PREVIEW)


@router.callback_query(FreeEpisodeForm.content_type, F.data.startswith("ctype:"))
async def free_content_type(callback: CallbackQuery, state: FSMContext) -> None:
    content = callback.data.split(":", 1)[1]
    await state.update_data(content_type=content)
    await state.set_state(FreeEpisodeForm.date)
    await callback.message.edit_text(
        f"✅ {content}\n\n📅 <b>Выберите желаемую дату съёмок:</b>",
        parse_mode="HTML", reply_markup=dates_kb())
    await callback.answer()


@router.callback_query(FreeEpisodeForm.date, F.data.startswith("bdate:"))
async def free_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await state.update_data(date=chosen_date)
    await state.set_state(FreeEpisodeForm.time)
    blocked = await get_booked_hours(chosen_date)
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n🕐 <b>Выберите время начала съёмок:</b>",
        parse_mode="HTML", reply_markup=times_kb(blocked))
    await callback.answer()


@router.callback_query(FreeEpisodeForm.time, F.data == "no_slots")
async def free_no_slots(callback: CallbackQuery) -> None:
    await callback.answer("На эту дату нет свободных слотов. Выберите другую дату.", show_alert=True)


@router.callback_query(FreeEpisodeForm.time, F.data.startswith("btime:"))
async def free_time(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_time = callback.data.split("btime:", 1)[1]
    await state.update_data(time=chosen_time)
    await state.set_state(FreeEpisodeForm.hours)
    await callback.message.edit_text(
        f"✅ {chosen_time}\n\n⏱ <b>Сколько часов нужна студия?</b>",
        parse_mode="HTML", reply_markup=hours_kb())
    await callback.answer()


@router.callback_query(FreeEpisodeForm.hours, F.data.startswith("bhours:"))
async def free_hours(callback: CallbackQuery, state: FSMContext) -> None:
    hours = callback.data.split(":", 1)[1]
    await state.update_data(hours=hours)
    await state.set_state(FreeEpisodeForm.phone)
    await callback.message.edit_text(
        f"✅ {hours} ч\n\n📱 <b>Укажите ваш номер телефона:</b>",
        parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()


@router.message(FreeEpisodeForm.phone)
async def free_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.clear()

    tg_id    = message.from_user.id
    username = message.from_user.username
    hours_int = int(data.get("hours", 1))

    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        fields = dict(
            name=data.get("name"), phone=phone,
            service=data.get("content_type"),
            booking_date=data.get("date"),
            booking_time=data.get("time"),
            booking_hours=hours_int,
            status="lead", lead_type="free_episode",
        )
        if client:
            for k, v in fields.items():
                setattr(client, k, v)
        else:
            session.add(Client(telegram_id=tg_id, username=username, **fields))
        await session.commit()

    summary = (
        "📋 <b>Ваша заявка</b>\n"
        f"├ 👤 Имя: <b>{data.get('name')}</b>\n"
        f"├ 📱 Телефон: <b>{phone}</b>\n"
        f"├ 🎬 Контент: <b>{data.get('content_type')}</b>\n"
        f"├ 📅 Дата: <b>{data.get('date')}</b>\n"
        f"├ 🕐 Время: <b>{data.get('time')}</b>\n"
        f"└ ⏱ Длительность: <b>{hours_int} ч</b>\n\n"
        "✅ <b>Спасибо за заявку!</b>\n"
        "└ Свяжемся с вами для подтверждения 🎙"
    )
    await message.answer(summary, parse_mode="HTML",
                         reply_markup=main_menu(), link_preview_options=NO_PREVIEW)

    admin_text = (
        "🔥 <b>Лид — Первый выпуск бесплатно</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 📱 {phone}\n"
        f"├ 🎬 {data.get('content_type')}\n"
        f"├ 📅 {data.get('date')} в {data.get('time')}\n"
        f"├ ⏱ {hours_int} ч\n"
        f"└ 📱 @{username or '—'} · <code>{tg_id}</code>"
    )
    try:
        await message.bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML",
                                       link_preview_options=NO_PREVIEW)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


# ─── CANCEL ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.message.answer("Выберите раздел меню 👇",
                                  reply_markup=main_menu(),
                                  link_preview_options=NO_PREVIEW)
    await callback.answer()
