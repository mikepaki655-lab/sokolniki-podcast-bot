import logging
import os
from datetime import datetime, timezone, timedelta

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy import select

from bot.keyboards import (
    cancel_kb,
    content_type_kb,
    dates_kb,
    free_episode_kb,
    hours_kb,
    main_menu,
    prices_kb,
    skip_cancel_kb,
    times_kb,
)
from bot.states import BookingForm, FreeEpisodeForm
from config import ADMIN_ID
from database.db import async_session, get_content
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images")
MOSCOW_TZ  = timezone(timedelta(hours=3))
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def is_working_hours() -> bool:
    now = datetime.now(MOSCOW_TZ)
    return now.weekday() < 5 and 9 <= now.hour < 18


async def send_section(message: Message, key: str, reply_markup=None) -> None:
    """Send section photo + text as one message (caption)."""
    section = await get_content(key)
    if not section:
        return

    photo_sent = False

    if section.photo_file_id:
        try:
            await message.answer_photo(
                photo=section.photo_file_id,
                caption=section.text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            photo_sent = True
        except Exception:
            pass

    if not photo_sent and section.local_banner:
        path = os.path.join(IMAGES_DIR, section.local_banner)
        if os.path.exists(path):
            await message.answer_photo(
                photo=FSInputFile(path),
                caption=section.text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            photo_sent = True

    if not photo_sent:
        await message.answer(
            section.text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW,
        )


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == message.from_user.id)
        )
        if not result.scalar_one_or_none():
            session.add(Client(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            ))
            await session.commit()

    await send_section(message, "welcome", reply_markup=main_menu())


# ─── BOOKING FLOW ─────────────────────────────────────────────────────────────

@router.message(F.text == "🎬 Записать подкаст")
@router.callback_query(F.data == "go_booking")
async def booking_start(event, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingForm.name)

    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()

    await send_section(msg, "booking")
    await msg.answer(
        "👤 <b>Как вас зовут?</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Введите имя (минимум 2 символа).")
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.content_type)
    await message.answer(
        "🎬 <b>Какой контент хотите снимать?</b>",
        parse_mode="HTML",
        reply_markup=content_type_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(BookingForm.content_type, F.data.startswith("ctype:"))
async def booking_content_type(callback: CallbackQuery, state: FSMContext) -> None:
    content = callback.data.split(":", 1)[1]
    await state.update_data(content_type=content)
    await state.set_state(BookingForm.date)
    await callback.message.edit_text(
        f"✅ {content}\n\n"
        "📅 <b>Выберите желаемую дату съёмок:</b>",
        parse_mode="HTML",
        reply_markup=dates_kb(),
    )
    await callback.answer()


@router.callback_query(BookingForm.date, F.data.startswith("bdate:"))
async def booking_date(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback.data.split(":", 1)[1]
    await state.update_data(date=chosen_date)
    await state.set_state(BookingForm.time)
    await callback.message.edit_text(
        f"✅ {chosen_date}\n\n"
        "🕐 <b>Выберите время начала съёмок:</b>",
        parse_mode="HTML",
        reply_markup=times_kb(),
    )
    await callback.answer()


@router.callback_query(BookingForm.time, F.data.startswith("btime:"))
async def booking_time(callback: CallbackQuery, state: FSMContext) -> None:
    chosen_time = callback.data.split(":", 1)[1]
    await state.update_data(time=chosen_time)
    await state.set_state(BookingForm.hours)
    await callback.message.edit_text(
        f"✅ {chosen_time}\n\n"
        "⏱ <b>Сколько часов нужна студия?</b>",
        parse_mode="HTML",
        reply_markup=hours_kb(),
    )
    await callback.answer()


@router.callback_query(BookingForm.hours, F.data.startswith("bhours:"))
async def booking_hours(callback: CallbackQuery, state: FSMContext) -> None:
    hours = callback.data.split(":", 1)[1]
    await state.update_data(hours=hours)
    data  = await state.get_data()
    await state.clear()

    tg_id    = callback.from_user.id
    username = callback.from_user.username

    # Save to DB
    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        if client:
            client.name         = data.get("name")
            client.service      = data.get("content_type")
            client.date         = f"{data.get('date')} в {data.get('time')}"
            client.comment      = f"Длительность: {data.get('hours')} ч"
            client.status       = "new_request"
            client.lead_type    = "booking"
        else:
            session.add(Client(
                telegram_id=tg_id,
                username=username,
                name=data.get("name"),
                service=data.get("content_type"),
                date=f"{data.get('date')} в {data.get('time')}",
                comment=f"Длительность: {data.get('hours')} ч",
                status="new_request",
                lead_type="booking",
            ))
        await session.commit()

    # Summary to client
    summary = (
        "📋 <b>Ваша заявка</b>\n"
        f"├ 👤 Имя: <b>{data.get('name')}</b>\n"
        f"├ 🎬 Контент: <b>{data.get('content_type')}</b>\n"
        f"├ 📅 Дата: <b>{data.get('date')}</b>\n"
        f"├ 🕐 Время: <b>{data.get('time')}</b>\n"
        f"└ ⏱ Длительность: <b>{data.get('hours')} ч</b>\n\n"
        "✅ <b>Спасибо за заявку!</b>\n"
        "└ Скоро с вами свяжемся 🎙"
    )
    await callback.message.edit_text(
        summary,
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
    )
    await callback.message.answer(
        "Выберите раздел меню 👇",
        reply_markup=main_menu(),
        link_preview_options=NO_PREVIEW,
    )
    await callback.answer()

    # Notify admin
    admin_text = (
        "🔥 <b>Новая заявка на съёмку</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 🎬 {data.get('content_type')}\n"
        f"├ 📅 {data.get('date')} в {data.get('time')}\n"
        f"├ ⏱ {data.get('hours')} ч\n"
        f"└ 📱 @{username or '—'} · <code>{tg_id}</code>"
    )
    try:
        await callback.bot.send_message(
            ADMIN_ID, admin_text, parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )
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


# ─── FREE EPISODE ─────────────────────────────────────────────────────────────

@router.message(F.text == "🔥 Первый выпуск бесплатно")
async def show_free_episode(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_section(message, "free", reply_markup=free_episode_kb())


@router.callback_query(F.data == "go_free_episode")
async def start_free_episode_form(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FreeEpisodeForm.name)
    await callback.message.answer(
        "🎁 <b>Анкета на бесплатный выпуск</b>\n\nКак вас зовут?",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.name)
async def free_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(FreeEpisodeForm.phone)
    await message.answer(
        "📱 <b>Ваш номер телефона:</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.phone)
async def free_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await state.set_state(FreeEpisodeForm.social_link)
    await message.answer(
        "🔗 <b>Ссылка на ваши соцсети</b>\n<i>Instagram, VK, YouTube и т.д.</i>",
        parse_mode="HTML",
        reply_markup=skip_cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(FreeEpisodeForm.social_link, F.data == "skip")
async def free_skip_social(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(social_link="—")
    await state.set_state(FreeEpisodeForm.occupation)
    await callback.message.edit_text(
        "💼 <b>Чем вы занимаетесь?</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(FreeEpisodeForm.social_link)
async def free_social(message: Message, state: FSMContext) -> None:
    await state.update_data(social_link=message.text.strip())
    await state.set_state(FreeEpisodeForm.occupation)
    await message.answer(
        "💼 <b>Чем вы занимаетесь?</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.occupation)
async def free_occupation(message: Message, state: FSMContext) -> None:
    await state.update_data(occupation=message.text.strip())
    await state.set_state(FreeEpisodeForm.podcast_goal)
    await message.answer(
        "🎯 <b>Зачем вам нужен подкаст?</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.podcast_goal)
async def free_goal(message: Message, state: FSMContext) -> None:
    await state.update_data(podcast_goal=message.text.strip())
    data     = await state.get_data()
    await state.clear()

    tg_id    = message.from_user.id
    username = message.from_user.username

    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        if client:
            client.name         = data.get("name")
            client.phone        = data.get("phone")
            client.social_link  = data.get("social_link")
            client.occupation   = data.get("occupation")
            client.podcast_goal = data.get("podcast_goal")
            client.status       = "lead"
            client.lead_type    = "free_episode"
        else:
            session.add(Client(
                telegram_id=tg_id, username=username,
                name=data.get("name"), phone=data.get("phone"),
                social_link=data.get("social_link"), occupation=data.get("occupation"),
                podcast_goal=data.get("podcast_goal"), status="lead", lead_type="free_episode",
            ))
        await session.commit()

    admin_text = (
        "🔥 <b>Новый лид — Бесплатный выпуск</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 📱 {data.get('phone')}\n"
        f"├ 🔗 {data.get('social_link')}\n"
        f"├ 💼 {data.get('occupation')}\n"
        f"├ 🎯 {data.get('podcast_goal')}\n"
        f"└ 📱 @{username or '—'} · <code>{tg_id}</code>"
    )
    try:
        await message.bot.send_message(
            ADMIN_ID, admin_text, parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")

    await message.answer(
        "✅ <b>Анкета отправлена!</b>\n"
        "└ Свяжемся с вами для подтверждения даты 🎙",
        parse_mode="HTML",
        reply_markup=main_menu(),
        link_preview_options=NO_PREVIEW,
    )


# ─── CANCEL ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.message.answer(
        "Выберите раздел меню 👇",
        reply_markup=main_menu(),
        link_preview_options=NO_PREVIEW,
    )
    await callback.answer()
