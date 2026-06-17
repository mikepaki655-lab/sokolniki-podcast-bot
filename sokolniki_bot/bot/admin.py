import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from sqlalchemy import func, select

from bot.keyboards import (
    admin_broadcast_target_kb,
    admin_client_actions_kb,
    admin_main_kb,
    back_to_admin_kb,
    broadcast_confirm_kb,
    content_back_to_section_kb,
    content_edit_kb,
    content_sections_kb,
)
from bot.states import BroadcastForm, EditContent, PaymentForm
from config import ADMIN_ID
from database.db import (
    async_session,
    get_all_content,
    get_content,
    reset_content_to_defaults,
    update_content_photo,
    update_content_text,
)
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

STATUS_LABELS = {
    "lead":        "🟡 Лид",
    "new_request": "🔵 Заявка",
    "paid":        "🟢 Оплатил",
    "completed":   "✅ Завершён",
}
TARGET_LABELS = {
    "lead":        "🔥 Лиды",
    "new_request": "📅 Заявки",
    "paid":        "💰 Оплатившие",
    "all":         "👥 Все клиенты",
}


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


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
        reply_markup=admin_main_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.clear()
    await callback.message.edit_text(
        "🎛 <b>Панель управления</b>\n└ Выберите раздел:",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()


# ─── ANALYTICS ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:analytics")
async def admin_analytics(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return

    now = datetime.now(timezone.utc)
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    async with async_session() as session:

        async def cnt(since: datetime, status: str | None = None) -> int:
            q = select(func.count()).select_from(Client).where(Client.created_at >= since)
            if status:
                q = q.where(Client.status == status)
            return (await session.execute(q)).scalar_one()

        async def rev(since: datetime) -> float:
            q = select(func.sum(Client.payment_amount)).where(
                Client.created_at >= since,
                Client.status == "paid",
                Client.payment_amount.isnot(None),
            )
            return (await session.execute(q)).scalar_one() or 0.0

        w = dict(leads=await cnt(week_ago,"lead"), req=await cnt(week_ago,"new_request"),
                 paid=await cnt(week_ago,"paid"), rev=await rev(week_ago))
        m = dict(leads=await cnt(month_ago,"lead"), req=await cnt(month_ago,"new_request"),
                 paid=await cnt(month_ago,"paid"), rev=await rev(month_ago))

    await callback.message.edit_text(
        "📊 <b>Аналитика</b>\n\n"
        "📅 <b>За 7 дней</b>\n"
        f"├ 🔥 Лиды: <b>{w['leads']}</b>\n"
        f"├ 📅 Заявки: <b>{w['req']}</b>\n"
        f"├ 💰 Оплаты: <b>{w['paid']}</b>\n"
        f"└ 💵 Выручка: <b>{w['rev']:,.0f} ₽</b>\n\n"
        "📅 <b>За 30 дней</b>\n"
        f"├ 🔥 Лиды: <b>{m['leads']}</b>\n"
        f"├ 📅 Заявки: <b>{m['req']}</b>\n"
        f"├ 💰 Оплаты: <b>{m['paid']}</b>\n"
        f"└ 💵 Выручка: <b>{m['rev']:,.0f} ₽</b>",
        parse_mode="HTML",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()


# ─── CLIENTS ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:clients")
async def admin_clients(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return

    async with async_session() as session:
        now = datetime.now(timezone.utc)
        total    = (await session.execute(select(func.count()).select_from(Client))).scalar_one()
        week_new = (await session.execute(
            select(func.count()).select_from(Client)
            .where(Client.created_at >= now - timedelta(days=7))
        )).scalar_one()
        month_new = (await session.execute(
            select(func.count()).select_from(Client)
            .where(Client.created_at >= now - timedelta(days=30))
        )).scalar_one()
        clients = (await session.execute(
            select(Client).order_by(Client.created_at.desc()).limit(20)
        )).scalars().all()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for c in clients:
        name  = c.name or "—"
        badge = STATUS_LABELS.get(c.status, c.status)
        builder.button(text=f"👤 {name}  {badge}", callback_data=f"admin:client:{c.id}")
    builder.button(text="◀️ В панель", callback_data="admin:back")
    builder.adjust(1)

    await callback.message.edit_text(
        "👥 <b>Клиенты</b>\n"
        f"├ Всего: <b>{total}</b>\n"
        f"├ За неделю: <b>{week_new}</b>\n"
        f"└ За месяц: <b>{month_new}</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:client:"))
async def admin_client_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return

    client_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        client = await session.get(Client, client_id)

    if not client:
        await callback.answer("Клиент не найден.")
        return

    tg      = f"@{client.username}" if client.username else f"ID:{client.telegram_id}"
    created = client.created_at.strftime("%d.%m.%Y %H:%M") if client.created_at else "—"
    payment = f"{client.payment_amount:,.0f} ₽" if client.payment_amount else "—"

    await callback.message.edit_text(
        f"👤 <b>{client.name or 'Без имени'}</b>\n\n"
        f"🪪 <b>Данные</b>\n"
        f"├ Telegram: {tg}\n"
        f"├ Телефон: {client.phone or '—'}\n"
        f"└ Создан: {created}\n\n"
        f"🎙 <b>Заявка</b>\n"
        f"├ Тип: {client.client_type or '—'}\n"
        f"├ Услуга: {client.service or '—'}\n"
        f"├ Дата записи: {client.date or '—'}\n"
        f"└ Комментарий: {client.comment or '—'}\n\n"
        f"📋 <b>CRM</b>\n"
        f"├ Статус: {STATUS_LABELS.get(client.status, client.status)}\n"
        f"├ Оплата: {payment}\n"
        f"├ Соцсети: {client.social_link or '—'}\n"
        f"├ Деятельность: {client.occupation or '—'}\n"
        f"└ Цель подкаста: {client.podcast_goal or '—'}",
        parse_mode="HTML",
        reply_markup=admin_client_actions_kb(client_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setstatus:"))
async def set_client_status(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return

    _, client_id_str, new_status = callback.data.split(":")
    client_id = int(client_id_str)

    if new_status == "paid":
        await state.set_state(PaymentForm.amount)
        await state.update_data(client_id=client_id)
        await callback.message.answer(
            "💰 Введите сумму оплаты (только цифры):",
            link_preview_options=NO_PREVIEW,
        )
        await callback.answer()
        return

    async with async_session() as session:
        client = await session.get(Client, client_id)
        if client:
            client.status = new_status
            await session.commit()

    await callback.answer(f"✅ {STATUS_LABELS.get(new_status, new_status)}")
    await admin_client_detail(callback)


@router.message(PaymentForm.amount)
async def payment_amount(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Введите корректную сумму.")
        return

    data = await state.get_data()
    await state.clear()

    async with async_session() as session:
        client = await session.get(Client, data.get("client_id"))
        if client:
            client.status = "paid"
            client.payment_amount = amount
            await session.commit()

    await message.answer(
        f"✅ <b>Статус → 🟢 Оплатил</b>\n└ Сумма: <b>{amount:,.0f} ₽</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
        link_preview_options=NO_PREVIEW,
    )


# ─── LEADS / REQUESTS / PAYMENTS ──────────────────────────────────────────────

@router.callback_query(F.data == "admin:leads")
async def admin_leads(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await _show_by_status(callback, "lead", "🔥 Лиды")

@router.callback_query(F.data == "admin:requests")
async def admin_requests(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await _show_by_status(callback, "new_request", "📅 Заявки")

@router.callback_query(F.data == "admin:payments")
async def admin_payments(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await _show_by_status(callback, "paid", "💰 Оплатившие")


async def _show_by_status(callback: CallbackQuery, status: str, title: str) -> None:
    async with async_session() as session:
        clients = (await session.execute(
            select(Client).where(Client.status == status)
            .order_by(Client.created_at.desc())
        )).scalars().all()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    if not clients:
        builder.button(text="◀️ В панель", callback_data="admin:back")
        await callback.message.edit_text(
            f"{title}\n└ Список пуст", reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    for c in clients:
        name     = c.name or "—"
        date_str = c.created_at.strftime("%d.%m") if c.created_at else "—"
        builder.button(text=f"👤 {name} · {date_str}", callback_data=f"admin:client:{c.id}")
    builder.button(text="◀️ В панель", callback_data="admin:back")
    builder.adjust(1)

    await callback.message.edit_text(
        f"{title}\n└ <b>{len(clients)}</b> чел.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


# ─── BROADCAST ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await state.set_state(BroadcastForm.target)
    await callback.message.edit_text(
        "📨 <b>Рассылка</b>\n└ Кому отправить?",
        parse_mode="HTML",
        reply_markup=admin_broadcast_target_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast_target:"))
async def broadcast_choose_target(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    target = callback.data.split(":", 1)[1]
    await state.update_data(target=target)
    await state.set_state(BroadcastForm.message)
    await callback.message.edit_text(
        f"📨 <b>Рассылка</b>\n"
        f"├ Кому: <b>{TARGET_LABELS.get(target, target)}</b>\n"
        f"└ Введите текст сообщения:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BroadcastForm.message)
async def broadcast_get_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastForm.confirm)
    data = await state.get_data()
    await message.answer(
        f"📨 <b>Подтверждение рассылки</b>\n"
        f"├ Кому: <b>{TARGET_LABELS.get(data.get('target'), data.get('target'))}</b>\n"
        f"└ Текст:\n\n<i>{message.text}</i>\n\nОтправить?",
        parse_mode="HTML",
        reply_markup=broadcast_confirm_kb(),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(F.data == "broadcast_confirm:yes")
async def broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    data   = await state.get_data()
    target = data.get("target")
    text   = data.get("broadcast_text", "")
    await state.clear()

    async with async_session() as session:
        q = select(Client.telegram_id)
        if target != "all":
            q = q.where(Client.status == target)
        ids = [row[0] for row in (await session.execute(q)).fetchall()]

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
        parse_mode="HTML",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_confirm:no")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await admin_back(callback, state)


# ─── CONTENT EDITOR ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:content")
async def admin_content(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await state.clear()
    sections = await get_all_content()
    await callback.message.edit_text(
        "📝 <b>Редактор контента</b>\n"
        "├ Выберите раздел для редактирования\n"
        "└ Можно изменить <b>текст</b> и <b>фото</b>",
        parse_mode="HTML",
        reply_markup=content_sections_kb(sections),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("content:section:"))
async def content_section_detail(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    await state.clear()
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    if not section:
        await callback.answer("Раздел не найден.")
        return

    photo_status = "✅ Загружено" if section.photo_file_id else "📁 Стандартное"
    await callback.message.edit_text(
        f"📝 <b>{section.title}</b>\n\n"
        f"🖼 Фото: {photo_status}\n\n"
        f"<b>Текущий текст:</b>\n{section.text}",
        parse_mode="HTML",
        reply_markup=content_edit_kb(key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("content:edit_text:"))
async def content_start_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    await state.set_state(EditContent.edit_text)
    await state.update_data(editing_key=key)
    await callback.message.edit_text(
        f"✏️ <b>Редактирование текста</b>\n"
        f"└ Раздел: <b>{section.title}</b>\n\n"
        f"<b>Текущий текст:</b>\n"
        f"<code>{section.text}</code>\n\n"
        "Отправьте новый текст.\n"
        "<i>HTML-теги: &lt;b&gt; &lt;i&gt; &lt;code&gt;\n"
        "Дерево: ├ └ │</i>",
        parse_mode="HTML",
        reply_markup=content_back_to_section_kb(key),
    )
    await callback.answer()


@router.message(EditContent.edit_text)
async def content_save_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    key  = data.get("editing_key")
    await state.clear()
    await update_content_text(key, message.text)
    section = await get_content(key)
    await message.answer(
        f"✅ <b>Текст раздела «{section.title}» обновлён</b>\n\n"
        f"{message.text}",
        parse_mode="HTML",
        reply_markup=content_edit_kb(key),
        link_preview_options=NO_PREVIEW,
    )


@router.callback_query(F.data.startswith("content:edit_photo:"))
async def content_start_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    await state.set_state(EditContent.edit_photo)
    await state.update_data(editing_key=key)
    await callback.message.edit_text(
        f"🖼 <b>Замена фото</b>\n"
        f"├ Раздел: <b>{section.title}</b>\n"
        f"└ Рекомендуемый размер: <b>640×360</b>\n\n"
        "Отправьте новое фото:",
        parse_mode="HTML",
        reply_markup=content_back_to_section_kb(key),
    )
    await callback.answer()


@router.message(EditContent.edit_photo, F.photo)
async def content_save_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data    = await state.get_data()
    key     = data.get("editing_key")
    await state.clear()
    file_id = message.photo[-1].file_id
    await update_content_photo(key, file_id)
    section = await get_content(key)
    await message.answer(
        f"✅ <b>Фото раздела «{section.title}» обновлено</b>",
        parse_mode="HTML",
        reply_markup=content_edit_kb(key),
        link_preview_options=NO_PREVIEW,
    )


@router.message(EditContent.edit_photo)
async def content_photo_wrong_type(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    await message.answer("⚠️ Отправьте фото (не файл, не ссылку).")


@router.callback_query(F.data.startswith("content:preview:"))
async def content_preview(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("⛔"); return
    import os
    from aiogram.types import FSInputFile
    key     = callback.data.split(":", 2)[2]
    section = await get_content(key)
    IMAGES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images"
    )
    photo_sent = False
    if section.photo_file_id:
        try:
            await callback.message.answer_photo(photo=section.photo_file_id)
            photo_sent = True
        except Exception:
            pass
    if not photo_sent and section.local_banner:
        path = os.path.join(IMAGES_DIR, section.local_banner)
        if os.path.exists(path):
            await callback.message.answer_photo(photo=FSInputFile(path))

    await callback.message.answer(
        f"👁 <b>Предпросмотр: {section.title}</b>\n\n{section.text}",
        parse_mode="HTML",
        reply_markup=content_edit_kb(key),
        link_preview_options=NO_PREVIEW,
    )
    await callback.answer()


# ─── RESET CONTENT ────────────────────────────────────────────────────────────

@router.message(Command("reset_content"))
async def cmd_reset_content(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await reset_content_to_defaults()
    await message.answer(
        "✅ <b>Тексты всех разделов сброшены к стандартным</b>\n"
        "└ Загруженные фото сохранены",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
        link_preview_options=NO_PREVIEW,
    )
