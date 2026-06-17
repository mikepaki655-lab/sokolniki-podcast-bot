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
    client_type_kb,
    free_episode_kb,
    main_menu,
    prices_kb,
    service_kb,
    skip_cancel_kb,
)
from bot.states import BookingForm, FreeEpisodeForm
from config import ADMIN_ID
from database.db import async_session, get_content
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images")
MOSCOW_TZ = timezone(timedelta(hours=3))

# Disable link previews for all text messages — cleaner look
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def is_working_hours() -> bool:
    now = datetime.now(MOSCOW_TZ)
    return now.weekday() < 5 and 9 <= now.hour < 18


async def send_section(message: Message, key: str, reply_markup=None) -> None:
    """Send section: photo + text as one message (caption). Falls back to text-only if no photo."""
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


# ─── /start ──────────────────────────────────────────────────────────────────

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
async def booking_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingForm.name)
    await send_section(message, "booking", reply_markup=cancel_kb())


@router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(BookingForm.client_type)
    await message.answer(
        "👤 Кто вы?",
        reply_markup=client_type_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(BookingForm.client_type, F.data.startswith("type:"))
async def booking_type(callback: CallbackQuery, state: FSMContext) -> None:
    client_type = callback.data.split(":", 1)[1]
    await state.update_data(client_type=client_type)
    await state.set_state(BookingForm.service)
    await callback.message.edit_text(
        f"✅ {client_type}\n\n🎙 <b>Какая услуга нужна?</b>",
        parse_mode="HTML",
        reply_markup=service_kb(),
    )
    await callback.answer()


@router.callback_query(BookingForm.service, F.data.startswith("service:"))
async def booking_service(callback: CallbackQuery, state: FSMContext) -> None:
    service = callback.data.split(":", 1)[1]
    if service == "custom":
        await state.set_state(BookingForm.custom_service)
        await callback.message.edit_text(
            "✏️ <b>Свой вариант</b>\n\nОпишите, что именно вам нужно:",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    else:
        await state.update_data(service=service)
        await state.set_state(BookingForm.date)
        await callback.message.edit_text(
            "📅 <b>Желаемая дата записи</b>\n\n"
            "Введите дату\n"
            "<i>Например: 25 июня или 25.06.2025</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    await callback.answer()


@router.message(BookingForm.custom_service)
async def booking_custom_service(message: Message, state: FSMContext) -> None:
    await state.update_data(service=f"Свой вариант: {message.text.strip()}")
    await state.set_state(BookingForm.date)
    await message.answer(
        "📅 <b>Желаемая дата записи</b>\n\n"
        "Введите дату\n"
        "<i>Например: 25 июня или 25.06.2025</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(BookingForm.date)
async def booking_date(message: Message, state: FSMContext) -> None:
    await state.update_data(date=message.text.strip())
    await state.set_state(BookingForm.comment)
    await message.answer(
        "💬 <b>Комментарий</b>\n\n"
        "Есть пожелания или вопросы?\n"
        "Напишите или нажмите «Пропустить»",
        parse_mode="HTML",
        reply_markup=skip_cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(BookingForm.comment, F.data == "skip")
async def booking_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(comment="—")
    await _save_booking(callback.message, state, callback.from_user.id, callback.from_user.username)
    await callback.answer()


@router.message(BookingForm.comment)
async def booking_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text.strip())
    await _save_booking(message, state, message.from_user.id, message.from_user.username)


async def _save_booking(message: Message, state: FSMContext, tg_id: int, username: str | None) -> None:
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        if client:
            client.name = data.get("name")
            client.client_type = data.get("client_type")
            client.service = data.get("service")
            client.date = data.get("date")
            client.comment = data.get("comment")
            client.status = "new_request"
            client.lead_type = "booking"
        else:
            session.add(Client(
                telegram_id=tg_id, username=username,
                name=data.get("name"), client_type=data.get("client_type"),
                service=data.get("service"), date=data.get("date"),
                comment=data.get("comment"), status="new_request", lead_type="booking",
            ))
        await session.commit()

    # Notify admin with tree-style card
    admin_text = (
        "🔥 <b>Новая заявка</b>\n"
        f"├ 👤 {data.get('name')}\n"
        f"├ 🏷 {data.get('client_type')}\n"
        f"├ 🎙 {data.get('service')}\n"
        f"├ 📅 {data.get('date')}\n"
        f"├ 💬 {data.get('comment')}\n"
        f"└ 📱 @{username or '—'} · <code>{tg_id}</code>"
    )
    try:
        await message.bot.send_message(
            ADMIN_ID, admin_text, parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    reply = (
        "✅ <b>Заявка принята!</b>\n"
        "└ Свяжемся с вами в течение <b>30 минут</b> 🕐"
        if is_working_hours() else
        "✅ <b>Заявка принята!</b>\n"
        "└ Свяжемся с вами в ближайшее время 😊"
    )
    await message.answer(
        reply, parse_mode="HTML",
        reply_markup=main_menu(),
        link_preview_options=NO_PREVIEW,
    )


# ─── PRICES ───────────────────────────────────────────────────────────────────

@router.message(F.text == "💰 Узнать цены")
async def show_prices(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_section(message, "prices", reply_markup=prices_kb())


@router.callback_query(F.data == "go_booking")
async def prices_go_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BookingForm.name)
    await callback.message.answer(
        "🎬 <b>Запись подкаста</b>\n\nКак вас зовут?",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


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
        "📱 Ваш номер телефона:",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.phone)
async def free_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await state.set_state(FreeEpisodeForm.social_link)
    await message.answer(
        "🔗 Ссылка на ваши соцсети\n<i>Instagram, VK, YouTube и т.д.</i>",
        parse_mode="HTML",
        reply_markup=skip_cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(FreeEpisodeForm.social_link, F.data == "skip")
async def free_skip_social(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(social_link="—")
    await state.set_state(FreeEpisodeForm.occupation)
    await callback.message.edit_text(
        "💼 Чем вы занимаетесь?",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(FreeEpisodeForm.social_link)
async def free_social(message: Message, state: FSMContext) -> None:
    await state.update_data(social_link=message.text.strip())
    await state.set_state(FreeEpisodeForm.occupation)
    await message.answer(
        "💼 Чем вы занимаетесь?",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.occupation)
async def free_occupation(message: Message, state: FSMContext) -> None:
    await state.update_data(occupation=message.text.strip())
    await state.set_state(FreeEpisodeForm.podcast_goal)
    await message.answer(
        "🎯 Зачем вам нужен подкаст?",
        reply_markup=cancel_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.message(FreeEpisodeForm.podcast_goal)
async def free_goal(message: Message, state: FSMContext) -> None:
    await state.update_data(podcast_goal=message.text.strip())
    data = await state.get_data()
    await state.clear()

    tg_id = message.from_user.id
    username = message.from_user.username

    async with async_session() as session:
        result = await session.execute(select(Client).where(Client.telegram_id == tg_id))
        client = result.scalar_one_or_none()
        if client:
            client.name = data.get("name")
            client.phone = data.get("phone")
            client.social_link = data.get("social_link")
            client.occupation = data.get("occupation")
            client.podcast_goal = data.get("podcast_goal")
            client.status = "lead"
            client.lead_type = "free_episode"
        else:
            session.add(Client(
                telegram_id=tg_id, username=username,
                name=data.get("name"), phone=data.get("phone"),
                social_link=data.get("social_link"), occupation=data.get("occupation"),
                podcast_goal=data.get("podcast_goal"), status="lead", lead_type="free_episode",
            ))
        await session.commit()

    # Admin notification with tree-style card
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
        logger.error(f"Failed to notify admin: {e}")

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
