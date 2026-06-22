import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database.db import init_db, get_all_admin_usernames
from bot.handlers import router as user_router
from bot.admin import router as admin_router, load_extra_admins
from bot.scheduler import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    logger.info("Database initialized")

    # Load extra admin usernames into memory
    extra_admins = await get_all_admin_usernames()
    load_extra_admins(extra_admins)
    logger.info("Extra admins loaded: %d", len(extra_admins))

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Set command menu (the "/" button in Telegram)
    await bot.set_my_commands([
        BotCommand(command="start",  description="Главное меню"),
        BotCommand(command="cancel", description="Отмена действия"),
        BotCommand(command="admin",  description="Панель управления"),
    ])

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)
    dp.include_router(user_router)

    logger.info("Starting bot polling...")

    retry_delay = 5
    while True:
        try:
            # Drop any stale webhook / pending updates from previous run
            await bot.delete_webhook(drop_pending_updates=True)
            asyncio.create_task(reminder_loop(bot))
            await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            break  # clean stop
        except Exception as exc:
            logger.error("Polling error: %s — retrying in %ss", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
