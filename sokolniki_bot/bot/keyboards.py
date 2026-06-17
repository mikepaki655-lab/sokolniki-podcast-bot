from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎬 Записать подкаст"))
    builder.row(
        KeyboardButton(text="💰 Узнать цены"),
        KeyboardButton(text="📍 Адрес студии"),
    )
    builder.row(KeyboardButton(text="🔥 Первый выпуск бесплатно"))
    return builder.as_markup(resize_keyboard=True)


def client_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in ["Предприниматель", "Эксперт", "Блогер", "Компания", "Другое"]:
        builder.button(text=t, callback_data=f"type:{t}")
    builder.adjust(2)
    return builder.as_markup()


def service_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    services = [
        ("🎙 Только запись", "Только запись"),
        ("🎬 Запись + монтаж", "Запись + монтаж"),
        ("📱 Запись + нарезка Reels/Shorts", "Запись + нарезка Reels/Shorts"),
        ("🚀 Подкаст под ключ", "Подкаст под ключ (запись, монтаж видео, нарезка Reels/Shorts)"),
        ("🏢 Аренда студии", "Аренда студии"),
        ("✏️ Свой вариант", "custom"),
    ]
    for label, data in services:
        builder.button(text=label, callback_data=f"service:{data}")
    builder.adjust(1)
    return builder.as_markup()


def prices_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Записаться", callback_data="go_booking")
    return builder.as_markup()


def free_episode_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Записаться бесплатно", callback_data="go_free_episode")
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def skip_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Пропустить", callback_data="skip")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


# ─── ADMIN KEYBOARDS ──────────────────────────────────────────────────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Аналитика", callback_data="admin:analytics")
    builder.button(text="👥 Клиенты", callback_data="admin:clients")
    builder.button(text="📨 Рассылка", callback_data="admin:broadcast")
    builder.button(text="🔥 Лиды", callback_data="admin:leads")
    builder.button(text="📅 Заявки", callback_data="admin:requests")
    builder.button(text="💰 Оплаты", callback_data="admin:payments")
    builder.button(text="📝 Контент", callback_data="admin:content")
    builder.adjust(2)
    return builder.as_markup()


def admin_client_actions_kb(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🟡 Лид", callback_data=f"setstatus:{client_id}:lead")
    builder.button(text="🔵 Заявка", callback_data=f"setstatus:{client_id}:new_request")
    builder.button(text="🟢 Оплатил", callback_data=f"setstatus:{client_id}:paid")
    builder.button(text="✅ Завершён", callback_data=f"setstatus:{client_id}:completed")
    builder.button(text="◀️ Назад", callback_data="admin:clients")
    builder.adjust(2)
    return builder.as_markup()


def admin_broadcast_target_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Лиды", callback_data="broadcast_target:lead")
    builder.button(text="📅 Заявки", callback_data="broadcast_target:new_request")
    builder.button(text="💰 Оплатившие", callback_data="broadcast_target:paid")
    builder.button(text="👥 Все клиенты", callback_data="broadcast_target:all")
    builder.button(text="❌ Отмена", callback_data="admin:cancel_broadcast")
    builder.adjust(2)
    return builder.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm:yes")
    builder.button(text="❌ Отмена", callback_data="broadcast_confirm:no")
    builder.adjust(2)
    return builder.as_markup()


def back_to_admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ В панель", callback_data="admin:back")
    return builder.as_markup()


def content_sections_kb(sections: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sections:
        builder.button(text=s.title, callback_data=f"content:section:{s.key}")
    builder.button(text="◀️ В панель", callback_data="admin:back")
    builder.adjust(1)
    return builder.as_markup()


def content_edit_kb(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить текст", callback_data=f"content:edit_text:{key}")
    builder.button(text="🖼 Изменить фото", callback_data=f"content:edit_photo:{key}")
    builder.button(text="👁 Предпросмотр", callback_data=f"content:preview:{key}")
    builder.button(text="◀️ К разделам", callback_data="admin:content")
    builder.adjust(1)
    return builder.as_markup()


def content_back_to_section_kb(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=f"content:section:{key}")
    return builder.as_markup()


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
