import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import distinct

from bot.keyboards import (
    admin_bookings_menu, admin_broadcast_menu, admin_main_menu,
    broadcast_confirm_kb, content_back_to_section_kb, content_edit_kb,
    content_sections_kb, main_menu, new_booking_actions_kb,
    processing_booking_actions_kb,
)
from bot.states import AdminAction, BroadcastForm, EditContentFSM
from config import ADMIN_ID
from database.db import (
    async_session, get_all_content, get_analytics, get_booking_with_client,
    get_bookings_by_status, get_content, get_or_create_client,
    reset_content_to_defaults, update_booking_status,
    update_content_photo, update_content_text,
)
from database.models import Booking, Client

router = Router()
logger = logging.getLogger(__name__)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

NEW_STATUSES        = {"new_request", "lead"}
PROCESSING_STATUSES = {"confirmed", "recorded", "paid"}
DONE_STATUSES       = {"done_paid", "done_no_pay", "rescheduled_done"}

STATUS_LABELS = {
    "new_request":      "🆕 Новая",
    "lead":             "🔥 Лид",
    "confirmed":        "✅ Подтверждена",
    "recorded":         "🎬 Записан",
    "paid":             "💰 Оплатил",
    "done_paid":        "✅ Завершена (оплата)",
    "done_no_pay":      "❌ Завершена (без оплаты)",
    "rescheduled_done": "🔄 Перенесена",
}

CLIENT_MESSAGES = {
    "confirmed": (
        "✅ <b>Ваша бронь подтверждена!</b>\n\n"
        "└ Ждём вас в студии «Сокольники» 🎙\n"
        "   г. Москва, Песочный пер., дом 3"
    ),
    "recorded": (
        "🎬 <b>Спасибо за визит!</b>\n\n"
        "└ Ваш выпуск в работе — скоро пришлём результат 🎉"
    ),
    "paid": (
        "💰 <b>Оплата получена, спасибо!</b>\n\n"
        "└ Студия «Сокольники» рада сотрудничеству 🎙"
    ),
}


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ─── /admin ───────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.clear()
    await message.answer(
        "🎛 <b>Панель управления</b>\n└ Выберите раздел:",
        parse_mode="HTML", reply_markup=admin_main_menu(),
    )


@router.message(F.text == "◀️ Вернуться в бота")
async def back_to_bot(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("👋 Вы вышли из панели управления.",
                         reply_markup=main_menu())


# ─── ЗАЯВКИ ───────────────────────────────────────────────────────────────────

@router.message(F.text == "📋 Заявки")
async def admin_bookings(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("📋 <b>Заявки</b>\n└ Выберите раздел:",
                         parse_mode="HTML", reply_markup=admin_bookings_menu())


@router.message(F.text == "◀️ Назад к меню")
async def bookings_back(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("🎛 <b>Панель управления</b>",
                         parse_mode="HTML", reply_markup=admin_main_menu())


async def _show_bookings_list(message: Message, statuses: set, title: str) -> None:
    pairs = await get_bookings_by_status(statuses)

    if not pairs:
        await message.answer(f"{title}\n└ Список пуст", parse_mode="HTML")
        return

    builder = InlineKeyboardBuilder()
    for booking, client in pairs:
        name  = client.name or "—"
        d     = booking.booking_date or "?"
        t     = booking.booking_time or ""
        badge = STATUS_LABELS.get(booking.status, booking.status)
        reschedule = f" ↩{booking.reschedule_from}" if booking.reschedule_from else ""
        time_part  = f" {t}" if t else ""
        label = f"#{booking.id} {name} · {d}{time_part}{reschedule} · {badge}"
        builder.button(text=label[:60], callback_data=f"view_booking:{booking.id}")
    builder.adjust(1)

    await message.answer(
        f"{title}\n└ <b>{len(pairs)}</b> заявок",
        parse_mode="HTML", reply_markup=builder.as_markup(),
    )


@router.message(F.text == "🆕 Новые")
async def admin_new(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await _show_bookings_list(message, NEW_STATUSES, "🆕 <b>Новые заявки</b>")


@router.message(F.text == "⚙️ В обработке")
async def admin_processing(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await _show_bookings_list(message, PROCESSING_STATUSES, "⚙️ <b>В обработке</b>")


@router.message(F.text == "✅ Завершённые")
async def admin_done(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await _show_bookings_list(message, DONE_STATUSES, "✅ <b>Завершённые</b>")


# ─── BOOKING DETAIL ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("view_booking:"))
async def view_booking(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔"); return

    booking_id = int(callback.data.split(":")[1])
    pair = await get_booking_with_client(booking_id)
    if not pair:
        await callback.answer("Заявка не найдена."); return
    booking, client = pair

    tg      = f"@{client.username}" if client.username else f"<code>{client.telegram_id}</code>"
    created = booking.created_at.strftime("%d.%m.%Y %H:%M") if booking.created_at else "—"
    reschedule_note = f"\n├ ↩ Перенесена с: <b>{booking.reschedule_from}</b>" if booking.reschedule_from else ""
    note_line = f"\n└ 📝 {booking.status_note}" if booking.status_note else ""
    lead_icon = "🔥" if booking.lead_type == "free_episode" else "📋"

    text = (
        f"👤 <b>{client.name or 'Без имени'}</b> {lead_icon}\n\n"
        f"🪪 <b>Контакты</b>\n"
        f"├ Telegram: {tg}\n"
        f"└ Телефон: {client.phone or '—'}\n\n"
        f"🎬 <b>Заявка #{booking.id}</b>\n"
        f"├ Контент: {booking.content_type or '—'}\n"
        f"├ Дата: {booking.booking_date or '—'}\n"
        f"├ Время: {booking.booking_time or '—'}\n"
        f"├ Часов: {booking.booking_hours or '—'}\n"
        f"└ Создана: {created}\n\n"
        f"📋 <b>Статус:</b> {STATUS_LABELS.get(booking.status, booking.status)}"
        f"{reschedule_note}{note_line}"
    )

    if booking.status in NEW_STATUSES:
        kb = new_booking_actions_kb(booking.id)
    elif booking.status in PROCESSING_STATUSES:
        kb = processing_booking_actions_kb(booking.id)
    else:
        kb = None

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb,
                                  link_preview_options=NO_PREVIEW)
    await callback.answer()


# ─── STATUS TRANSITIONS ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bstatus:"))
async def set_booking_status(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔"); return

    parts = callback.data.split(":")
    booking_id = int(parts[1])
    new_status = parts[2]

    if new_status == "done_paid":
        await state.set_state(AdminAction.payment_amount)
        await state.update_data(target_booking_id=booking_id)
        await callback.message.answer(
            "💰 <b>Завершена с оплатой</b>\n└ Введите сумму оплаты (₽):",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    if new_status == "done_no_pay":
        await state.set_state(AdminAction.no_pay_reason)
        await state.update_data(target_booking_id=booking_id)
        await callback.message.answer(
            "❌ <b>Завершена без оплаты</b>\n└ Укажите причину:",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    if new_status == "reschedule":
        await state.set_state(AdminAction.reschedule_reason)
        await state.update_data(target_booking_id=booking_id)
        await callback.message.answer(
            "🔄 <b>Перенос заявки</b>\n└ Укажите причину переноса:",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    # Simple status update
    await update_booking_status(booking_id, status=new_status)

    label = STATUS_LABELS.get(new_status, new_status)
    await callback.answer(f"✅ {label}", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Notify client if applicable
    await _notify_client(callback, booking_id, new_status)


async def _notify_client(callback, booking_id: int, new_status: str) -> None:
    """Send status notification to client if a message template exists."""
    msg_text = CLIENT_MESSAGES.get(new_status)
    if not msg_text:
        return
    pair = await get_booking_with_client(booking_id)
    if not pair:
        return
    booking, client = pair
    try:
        await callback.bot.send_message(
            client.telegram_id, msg_text,
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
    except Exception as e:
        logger.warning(f"Client notify failed for {client.telegram_id}: {e}")


# ─── DONE WITH PAYMENT ────────────────────────────────────────────────────────

@router.message(AdminAction.payment_amount)
async def admin_payment_amount(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    try:
        amount = float(message.text.strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Введите число."); return

    await state.update_data(payment_amount=amount)
    await state.set_state(AdminAction.payment_hours)
    await message.answer("⏱ Сколько часов по факту?",
                         link_preview_options=NO_PREVIEW)


@router.message(AdminAction.payment_hours)
async def admin_payment_hours(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    try:
        hours = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("⚠️ Введите число."); return

    data = await state.get_data()
    await state.clear()
    booking_id = data["target_booking_id"]

    booking = await update_booking_status(
        booking_id,
        status="done_paid",
        payment_amount=data["payment_amount"],
        payment_hours=hours,
    )

    await message.answer(
        f"✅ <b>Завершена с оплатой</b>\n"
        f"├ Сумма: <b>{data['payment_amount']:,.0f} ₽</b>\n"
        f"└ Часов: <b>{hours}</b>",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)

    # Notify client
    pair = await get_booking_with_client(booking_id)
    if pair:
        _, client = pair
        try:
            await message.bot.send_message(
                client.telegram_id,
                "✅ <b>Спасибо за оплату!</b>\n\n"
                "Ваша бронь завершена. Ждём вас снова в студии «Сокольники» 🎙",
                parse_mode="HTML", link_preview_options=NO_PREVIEW)
        except Exception:
            pass


# ─── DONE WITHOUT PAYMENT ─────────────────────────────────────────────────────

@router.message(AdminAction.no_pay_reason)
async def admin_no_pay_reason(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()

    booking_id = data["target_booking_id"]
    await update_booking_status(
        booking_id,
        status="done_no_pay",
        status_note=message.text.strip(),
    )

    await message.answer(
        f"❌ <b>Завершена без оплаты</b>\n└ Причина: {message.text.strip()}",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── RESCHEDULE ───────────────────────────────────────────────────────────────

@router.message(AdminAction.reschedule_reason)
async def admin_reschedule_reason(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(reschedule_reason=message.text.strip())
    await state.set_state(AdminAction.reschedule_date)
    await message.answer("📅 Новая дата (например: 25.07.2026):",
                         link_preview_options=NO_PREVIEW)


@router.message(AdminAction.reschedule_date)
async def admin_reschedule_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(reschedule_new_date=message.text.strip())
    await state.set_state(AdminAction.reschedule_time)
    await message.answer("🕐 Новое время начала (например: 14:00):",
                         link_preview_options=NO_PREVIEW)


@router.message(AdminAction.reschedule_time)
async def admin_reschedule_time(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()

    booking_id   = data["target_booking_id"]
    new_date     = data["reschedule_new_date"]
    new_time     = message.text.strip()
    reason       = data.get("reschedule_reason", "")

    # Get current booking_date for reschedule_from
    pair = await get_booking_with_client(booking_id)
    old_date = pair[0].booking_date if pair else "?"

    await update_booking_status(
        booking_id,
        status="new_request",
        booking_date=new_date,
        booking_time=new_time,
        reschedule_from=old_date,
        status_note=reason,
        reminded=0,          # reset reminder so client gets reminder for new date
    )

    # Notify client
    if pair:
        _, client = pair
        try:
            await message.bot.send_message(
                client.telegram_id,
                f"🔄 <b>Ваша бронь перенесена</b>\n\n"
                f"├ 📅 Новая дата: <b>{new_date}</b>\n"
                f"├ 🕐 Время: <b>{new_time}</b>\n"
                f"└ Причина: {reason or '—'}\n\n"
                "Если удобно — ждём вас! Если нет — напишите нам 📩",
                parse_mode="HTML", link_preview_options=NO_PREVIEW)
        except Exception:
            pass

    await message.answer(
        f"🔄 <b>Заявка перенесена</b>\n"
        f"├ Новая дата: <b>{new_date}</b>\n"
        f"├ Новое время: <b>{new_time}</b>\n"
        f"└ Причина: {reason or '—'}\n\n"
        "Заявка появилась в разделе <b>🆕 Новые</b>.",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── АНАЛИТИКА ────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Аналитика")
async def admin_analytics(message: Message) -> None:
    if not is_admin(message.from_user.id): return

    stats = await get_analytics(days=7)

    await message.answer(
        "📊 <b>Аналитика за 7 дней</b>\n"
        "<i>(по дате съёмки)</i>\n\n"
        f"├ 🆕 Новых заявок: <b>{stats['new']}</b>\n"
        f"├ ⚙️ В обработке: <b>{stats['proc']}</b>\n"
        f"├ ✅ Завершено с оплатой: <b>{stats['done']}</b>\n"
        f"├ 💵 Выручка: <b>{stats['revenue']:,.0f} ₽</b>\n"
        f"└ ⏱ Часов отработано: <b>{stats['hours']:.1f} ч</b>",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── РАССЫЛКА ─────────────────────────────────────────────────────────────────

TARGET_MAP = {
    "📤 Всем":        "all",
    "📤 Новым":       "new_request",
    "📤 В обработке": "processing",
    "📤 Завершённым": "done",
}

@router.message(F.text == "📨 Рассылка")
async def admin_broadcast_menu_msg(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.clear()
    await message.answer("📨 <b>Рассылка</b>\n└ Кому отправить?",
                         parse_mode="HTML", reply_markup=admin_broadcast_menu())


@router.message(F.text.in_(TARGET_MAP.keys()))
async def broadcast_choose_target(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    target = TARGET_MAP[message.text]
    await state.update_data(broadcast_target=target)
    await state.set_state(BroadcastForm.message)
    await message.answer(
        f"📨 Кому: <b>{message.text}</b>\n\nВведите текст рассылки:",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


@router.message(BroadcastForm.message)
async def broadcast_get_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastForm.confirm)
    data = await state.get_data()
    await message.answer(
        f"📨 <b>Подтверждение рассылки</b>\n"
        f"├ Кому: <b>{data.get('broadcast_target')}</b>\n"
        f"└ Текст:\n\n<i>{message.text}</i>\n\nОтправить?",
        parse_mode="HTML",
        reply_markup=broadcast_confirm_kb(),
        link_preview_options=NO_PREVIEW)


@router.callback_query(F.data == "broadcast_confirm:yes")
async def broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    data   = await state.get_data()
    target = data.get("broadcast_target", "all")
    text   = data.get("broadcast_text", "")
    await state.clear()

    async with async_session() as session:
        q = select(Client.telegram_id)
        if target != "all":
            if target == "new_request":
                status_filter = NEW_STATUSES
            elif target == "processing":
                status_filter = PROCESSING_STATUSES
            else:
                status_filter = DONE_STATUSES
            q = (select(distinct(Client.telegram_id))
                 .join(Booking, Booking.client_id == Client.id)
                 .where(Booking.status.in_(status_filter)))
        ids = [r[0] for r in (await session.execute(q)).fetchall()]

    sent = failed = 0
    for tg_id in ids:
        try:
            await callback.bot.send_message(tg_id, text, parse_mode="HTML",
                                            link_preview_options=NO_PREVIEW)
            sent += 1
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n"
        f"├ 📤 Отправлено: <b>{sent}</b>\n"
        f"└ ❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "broadcast_confirm:no")
async def broadcast_cancel_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


# ─── CONTENT EDITOR ───────────────────────────────────────────────────────────

@router.message(F.text == "📝 Контент")
async def admin_content_menu(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.clear()
    sections = await get_all_content()
    await message.answer(
        "📝 <b>Редактор контента</b>\n└ Выберите раздел:",
        parse_mode="HTML", reply_markup=content_sections_kb(sections))


@router.callback_query(F.data == "admin:content")
async def admin_content_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await state.clear()
    sections = await get_all_content()
    await callback.message.answer(
        "📝 <b>Редактор контента</b>\n└ Выберите раздел:",
        parse_mode="HTML", reply_markup=content_sections_kb(sections))
    await callback.answer()


@router.callback_query(F.data.startswith("content:section:"))
async def content_section_detail(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await state.clear()
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    if not section:
        await callback.answer("Раздел не найден."); return
    photo_status = "✅ Загружено" if section.photo_file_id else "📁 Стандартное"
    await callback.message.answer(
        f"📝 <b>{section.title}</b>\n\n"
        f"🖼 Фото: {photo_status}\n\n"
        f"<b>Текущий текст:</b>\n{section.text}",
        parse_mode="HTML", reply_markup=content_edit_kb(key))
    await callback.answer()


@router.callback_query(F.data.startswith("content:edit_text:"))
async def content_start_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    await state.set_state(EditContentFSM.edit_text)
    await state.update_data(editing_key=key)
    await callback.message.answer(
        f"✏️ <b>Редактирование: {section.title}</b>\n\n"
        f"<b>Текущий текст:</b>\n<code>{section.text}</code>\n\n"
        "Отправьте новый текст (HTML-теги поддерживаются):",
        parse_mode="HTML", reply_markup=content_back_to_section_kb(key))
    await callback.answer()


@router.message(EditContentFSM.edit_text)
async def content_save_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    key  = data.get("editing_key")
    await state.clear()
    await update_content_text(key, message.text)
    section = await get_content(key)
    await message.answer(
        f"✅ <b>Текст обновлён: {section.title}</b>\n\n{message.text}",
        parse_mode="HTML", reply_markup=content_edit_kb(key),
        link_preview_options=NO_PREVIEW)


@router.callback_query(F.data.startswith("content:edit_photo:"))
async def content_start_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    key = callback.data.split(":", 2)[2]
    await state.set_state(EditContentFSM.edit_photo)
    await state.update_data(editing_key=key)
    await callback.message.answer(
        "🖼 Отправьте новое фото для раздела:",
        reply_markup=content_back_to_section_kb(key))
    await callback.answer()


@router.message(EditContentFSM.edit_photo)
async def content_save_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    if not message.photo:
        await message.answer("⚠️ Отправьте фото.")
        return
    data    = await state.get_data()
    key     = data.get("editing_key")
    file_id = message.photo[-1].file_id
    await state.clear()
    await update_content_photo(key, file_id)
    section = await get_content(key)
    await message.answer(
        f"✅ <b>Фото обновлено: {section.title}</b>",
        parse_mode="HTML", reply_markup=content_edit_kb(key))


@router.callback_query(F.data.startswith("content:preview:"))
async def content_preview(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    if not section:
        await callback.answer("Раздел не найден."); return
    import os
    IMAGES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
    photo_sent = False
    if section.photo_file_id:
        try:
            await callback.message.answer_photo(
                photo=section.photo_file_id, caption=section.text,
                parse_mode="HTML")
            photo_sent = True
        except Exception:
            pass
    if not photo_sent and section.local_banner:
        from aiogram.types import FSInputFile
        path = os.path.join(IMAGES_DIR, section.local_banner)
        if os.path.exists(path):
            await callback.message.answer_photo(
                photo=FSInputFile(path), caption=section.text,
                parse_mode="HTML")
            photo_sent = True
    if not photo_sent:
        await callback.message.answer(section.text, parse_mode="HTML",
                                      link_preview_options=NO_PREVIEW)
    await callback.answer("👁 Предпросмотр")
