"""
Background scheduler: sends 24-hour reminders to clients before their booking.
Runs as an asyncio task inside the bot process — no extra dependencies needed.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from database.db import get_upcoming_bookings_for_reminder, mark_reminded

logger = logging.getLogger(__name__)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
CHECK_INTERVAL = 3600  # check every hour


async def send_reminders(bot: Bot) -> None:
    """Find bookings happening tomorrow and send reminder to each client."""
    pairs = await get_upcoming_bookings_for_reminder()
    for booking, client in pairs:
        try:
            text = (
                "⏰ <b>Напоминание о записи</b>\n\n"
                f"├ 📅 Дата: <b>{booking.booking_date}</b>\n"
                f"├ 🕐 Время: <b>{booking.booking_time}</b>\n"
                f"├ ⏱ Длительность: <b>{booking.booking_hours} ч</b>\n"
                "└ 📍 г. Москва, Песочный пер., дом 3\n\n"
                "Ждём вас в студии «Сокольники»! 🎙"
            )
            await bot.send_message(
                client.telegram_id, text,
                parse_mode="HTML",
                link_preview_options=NO_PREVIEW,
            )
            await mark_reminded(booking.id)
            logger.info(f"Reminder sent to {client.telegram_id} for booking {booking.id}")
        except Exception as e:
            logger.warning(f"Reminder failed for {client.telegram_id}: {e}")


async def reminder_loop(bot: Bot) -> None:
    """Infinite loop that checks and sends reminders every hour."""
    logger.info("Reminder scheduler started.")
    while True:
        try:
            await send_reminders(bot)
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)
