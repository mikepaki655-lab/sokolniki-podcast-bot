import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from bot.keyboards import (
    admin_bookings_menu, admin_broadcast_menu, admin_main_menu,
    broadcast_confirm_kb, content_back_to_section_kb, content_edit_kb,
    content_sections_kb, main_menu, new_booking_actions_kb,
    processing_booking_actions_kb,
)
from bot.states import AdminAction, BroadcastForm
from config import ADMIN_ID
from database.db import (
    async_session, get_all_content, get_content,
    reset_content_to_defaults, update_content_photo, update_content_text,
)
from database.models import Client
from bot.states import AdminAction

router = Router()
logger = logging.getLogger(__name__)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# Statuses shown in each tab
NEW_STATUSES        = {"new_request", "lead"}
PROCESSING_STATUSES = {"confirmed", "recorded", "paid"}
DONE_STATUSES       = {"done_paid", "done_no_pay", "rescheduled_done"}

STATUS_LABELS = {
    "new_request":     "🆕 Новая",
    "lead":            "🔥 Лид",
    "confirmed":       "✅ Подтверждена",
    "recorded":        "🎬 Записан",
    "paid":            "💰 Оплатил",
    "done_paid":       "✅ Завершена (оплата)",
    "done_no_pay":     "❌ Завершена (без оплаты)",
    "rescheduled_done":"🔄 Перенесена",
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
        parse_mode="HTML",
        reply_markup=admin_main_menu(),
    )


# ─── ВЕРНУТЬСЯ В БОТА ─────────────────────────────────────────────────────────

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
    async with async_session() as session:
        clients = (await session.execute(
            select(Client)
            .where(Client.status.in_(statuses))
            .order_by(Client.created_at.desc())
            .limit(50)
        )).scalars().all()

    if not clients:
        await message.answer(f"{title}\n└ Список пуст", parse_mode="HTML")
        return

    builder = InlineKeyboardBuilder()
    for c in clients:
        name     = c.name or "—"
        d        = c.booking_date or "?"
        badge    = STATUS_LABELS.get(c.status, c.status)
        reschedule = f" ↩{c.reschedule_from}" if c.reschedule_from else ""
        label = f"{name} · {d}{reschedule} · {badge}"
        builder.button(text=label[:60], callback_data=f"view_client:{c.id}")
    builder.adjust(1)

    await message.answer(
        f"{title}\n└ <b>{len(clients)}</b> заявок",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
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


# ─── CLIENT DETAIL ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("view_client:"))
async def view_client(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔"); return
    client_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        client = await session.get(Client, client_id)
    if not client:
        await callback.answer("Клиент не найден."); return

    tg      = f"@{client.username}" if client.username else f"<code>{client.telegram_id}</code>"
    created = client.created_at.strftime("%d.%m.%Y %H:%M") if client.created_at else "—"
    reschedule_note = f"\n├ ↩ Перенесена с: <b>{client.reschedule_from}</b>" if client.reschedule_from else ""
    note_line = f"\n└ 📝 {client.status_note}" if client.status_note else ""

    text = (
        f"👤 <b>{client.name or 'Без имени'}</b>\n\n"
        f"🪪 <b>Контакты</b>\n"
        f"├ Telegram: {tg}\n"
        f"└ Телефон: {client.phone or '—'}\n\n"
        f"🎬 <b>Заявка</b>\n"
        f"├ Контент: {client.service or '—'}\n"
        f"├ Дата: {client.booking_date or '—'}\n"
        f"├ Время: {client.booking_time or '—'}\n"
        f"├ Часов: {client.booking_hours or '—'}\n"
        f"└ Создана: {created}\n\n"
        f"📋 <b>Статус:</b> {STATUS_LABELS.get(client.status, client.status)}"
        f"{reschedule_note}{note_line}"
    )

    # Choose action keyboard based on current status
    if client.status in NEW_STATUSES:
        kb = new_booking_actions_kb(client_id)
    elif client.status in PROCESSING_STATUSES:
        kb = processing_booking_actions_kb(client_id)
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

    _, client_id_str, new_status = callback.data.split(":")
    client_id = int(client_id_str)

    if new_status == "done_paid":
        await state.set_state(AdminAction.payment_amount)
        await state.update_data(target_client_id=client_id)
        await callback.message.answer(
            "💰 <b>Завершена с оплатой</b>\n└ Введите сумму оплаты (₽):",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    if new_status == "done_no_pay":
        await state.set_state(AdminAction.no_pay_reason)
        await state.update_data(target_client_id=client_id)
        await callback.message.answer(
            "❌ <b>Завершена без оплаты</b>\n└ Укажите причину:",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    if new_status == "reschedule":
        await state.set_state(AdminAction.reschedule_reason)
        await state.update_data(target_client_id=client_id)
        await callback.message.answer(
            "🔄 <b>Перенос заявки</b>\n└ Укажите причину переноса:",
            parse_mode="HTML", link_preview_options=NO_PREVIEW)
        await callback.answer(); return

    # Simple status update (confirmed / recorded / paid)
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if client:
            client.status = new_status
            await session.commit()

    label = STATUS_LABELS.get(new_status, new_status)
    await callback.answer(f"✅ {label}", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


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
    await message.answer("⏱ Сколько часов по факту (введите число)?",
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
    client_id = data["target_client_id"]

    async with async_session() as session:
        client = await session.get(Client, client_id)
        if client:
            client.status         = "done_paid"
            client.payment_amount = data["payment_amount"]
            client.payment_hours  = hours
            await session.commit()

    await message.answer(
        f"✅ <b>Завершена с оплатой</b>\n"
        f"├ Сумма: <b>{data['payment_amount']:,.0f} ₽</b>\n"
        f"└ Часов: <b>{hours}</b>",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── DONE WITHOUT PAYMENT ────────────────────────────────────────────────────

@router.message(AdminAction.no_pay_reason)
async def admin_no_pay_reason(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        client = await session.get(Client, data["target_client_id"])
        if client:
            client.status      = "done_no_pay"
            client.status_note = message.text.strip()
            await session.commit()

    await message.answer(
        f"❌ <b>Завершена без оплаты</b>\n└ Причина: {message.text.strip()}",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── RESCHEDULE ───────────────────────────────────────────────────────────────

@router.message(AdminAction.reschedule_reason)
async def admin_reschedule_reason(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(reschedule_reason=message.text.strip())
    await state.set_state(AdminAction.reschedule_date)
    await message.answer("📅 Введите новую дату (например: 25.06.2026):",
                         link_preview_options=NO_PREVIEW)


@router.message(AdminAction.reschedule_date)
async def admin_reschedule_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(reschedule_new_date=message.text.strip())
    await state.set_state(AdminAction.reschedule_hours)
    await message.answer("⏱ Кол-во часов для новой брони:",
                         link_preview_options=NO_PREVIEW)


@router.message(AdminAction.reschedule_hours)
async def admin_reschedule_hours(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    try:
        hours = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Введите число."); return

    data = await state.get_data()
    await state.clear()
    client_id = data["target_client_id"]

    async with async_session() as session:
        client = await session.get(Client, client_id)
        if client:
            old_date             = client.booking_date
            client.reschedule_from = old_date
            client.booking_date  = data["reschedule_new_date"]
            client.booking_hours = hours
            client.status        = "new_request"
            client.status_note   = data.get("reschedule_reason", "")
            await session.commit()

    await message.answer(
        f"🔄 <b>Заявка перенесена</b>\n"
        f"├ Новая дата: <b>{data['reschedule_new_date']}</b>\n"
        f"├ Часов: <b>{hours}</b>\n"
        f"└ Причина: {data.get('reschedule_reason','—')}\n\n"
        "Заявка появилась в разделе <b>🆕 Новые</b> с пометкой о переносе.",
        parse_mode="HTML", link_preview_options=NO_PREVIEW)


# ─── АНАЛИТИКА ────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Аналитика")
async def admin_analytics(message: Message) -> None:
    if not is_admin(message.from_user.id): return

    now      = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    async with async_session() as session:
        async def cnt(since, *filters):
            q = select(func.count()).select_from(Client).where(
                Client.created_at >= since, *filters)
            return (await session.execute(q)).scalar_one()

        async def sum_col(col, since):
            q = select(func.sum(col)).where(
                Client.created_at >= since, col.isnot(None))
            return (await session.execute(q)).scalar_one() or 0

        new_w   = await cnt(week_ago, Client.status.in_(NEW_STATUSES))
        proc_w  = await cnt(week_ago, Client.status.in_(PROCESSING_STATUSES))
        done_w  = await cnt(week_ago, Client.status == "done_paid")
        revenue = await sum_col(Client.payment_amount, week_ago)
        hours   = await sum_col(Client.payment_hours, week_ago)

    await message.answer(
        "📊 <b>Аналитика за 7 дней</b>\n\n"
        f"├ 🆕 Новых заявок: <b>{new_w}</b>\n"
        f"├ ⚙️ В обработке: <b>{proc_w}</b>\n"
        f"├ ✅ Завершено с оплатой: <b>{done_w}</b>\n"
        f"├ 💵 Выручка: <b>{revenue:,.0f} ₽</b>\n"
        f"└ ⏱ Часов забронировано: <b>{hours:.1f} ч</b>",
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
        f"📨 <b>Подтверждение</b>\n"
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
        if target == "new_request":
            q = q.where(Client.status.in_(NEW_STATUSES))
        elif target == "processing":
            q = q.where(Client.status.in_(PROCESSING_STATUSES))
        elif target == "done":
            q = q.where(Client.status.in_(DONE_STATUSES))
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

from aiogram.fsm.state import State, StatesGroup

class EditContentFSM(StatesGroup):
    edit_text  = State()
    edit_photo = State()


@router.callback_query(F.data == "admin:content")
async def admin_content(callback: CallbackQuery, state: FSMContext) -> None:
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
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    await state.set_state(EditContentFSM.edit_photo)
    await state.update_data(editing_key=key)
    await callback.message.answer(
        f"🖼 <b>Замена фото: {section.title}</b>\n"
        "└ Рекомендуемый размер: 640×360\n\nОтправьте новое фото:",
        parse_mode="HTML", reply_markup=content_back_to_section_kb(key))
    await callback.answer()


@router.message(EditContentFSM.edit_photo, F.photo)
async def content_save_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data    = await state.get_data()
    key     = data.get("editing_key")
    await state.clear()
    file_id = message.photo[-1].file_id
    await update_content_photo(key, file_id)
    section = await get_content(key)
    await message.answer(f"✅ <b>Фото обновлено: {section.title}</b>",
                         parse_mode="HTML", reply_markup=content_edit_kb(key),
                         link_preview_options=NO_PREVIEW)


@router.message(EditContentFSM.edit_photo)
async def content_photo_wrong(message: Message) -> None:
    await message.answer("⚠️ Отправьте фото (не файл, не ссылку).")


@router.callback_query(F.data.startswith("content:preview:"))
async def content_preview(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    import os
    from aiogram.types import FSInputFile
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    IMAGES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
    photo_sent = False
    if section.photo_file_id:
        try:
            await callback.message.answer_photo(
                photo=section.photo_file_id, caption=section.text,
                parse_mode="HTML", reply_markup=content_edit_kb(key))
            photo_sent = True
        except Exception:
            pass
    if not photo_sent and section.local_banner:
        path = os.path.join(IMAGES_DIR, section.local_banner)
        if os.path.exists(path):
            await callback.message.answer_photo(
                photo=FSInputFile(path), caption=section.text,
                parse_mode="HTML", reply_markup=content_edit_kb(key))
    await callback.answer()


@router.message(Command("reset_content"))
async def cmd_reset_content(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён."); return
    await reset_content_to_defaults()
    await message.answer("✅ <b>Тексты сброшены к стандартным</b>",
                         parse_mode="HTML")
