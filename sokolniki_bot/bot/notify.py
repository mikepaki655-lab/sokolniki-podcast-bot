"""Helpers for broadcasting notifications to all admins."""
import logging

from config import ADMIN_ID
from database.db import get_all_admin_telegram_ids

logger = logging.getLogger(__name__)


async def notify_admins(bot, text: str, **kwargs) -> None:
    """Send a message to the owner AND every extra admin that has a known telegram_id."""
    tg_ids = await get_all_admin_telegram_ids()
    for tg_id in tg_ids:
        try:
            await bot.send_message(tg_id, text, **kwargs)
        except Exception as e:
            logger.warning("notify_admins: failed to send to %s: %s", tg_id, e)
