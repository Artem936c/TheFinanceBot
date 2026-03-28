from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.init_db import init_db
from app.services.scheduler_service import start_scheduler

settings = get_settings()

if settings.telegram_enabled:
    from app.bot.telegram.bot import telegram_bot, telegram_dp
    from app.bot.telegram.handlers import telegram_router
else:
    telegram_bot = None
    telegram_dp = None
    telegram_router = None

if settings.max_enabled:
    from app.bot.max.bot import max_bot, max_dp
    import app.bot.max.handlers  # noqa: F401
else:
    max_bot = None
    max_dp = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
)
logger = logging.getLogger(__name__)


async def run_telegram() -> None:
    if not settings.telegram_enabled:
        logger.info('Telegram bot is disabled by TELEGRAM_ENABLED=false.')
        return
    if not telegram_bot or not telegram_dp or not telegram_router:
        logger.warning('Telegram is enabled, but TELEGRAM_BOT_TOKEN is not configured.')
        return
    telegram_dp.include_router(telegram_router)
    logger.info('Starting Telegram polling')
    await telegram_dp.start_polling(telegram_bot)


async def run_max() -> None:
    if not settings.max_enabled:
        logger.info('MAX bot is disabled by MAX_ENABLED=false.')
        return
    if not max_bot or not max_dp:
        logger.warning('MAX is enabled, but MAX_BOT_TOKEN is not configured or maxapi is unavailable.')
        return
    logger.info('Starting MAX polling')
    try:
        if hasattr(max_bot, 'delete_webhook'):
            await max_bot.delete_webhook()
    except Exception as exc:
        logger.warning('Unable to delete MAX webhook before polling: %s', exc)
    await max_dp.start_polling(max_bot)


async def main() -> None:
    await init_db()
    start_scheduler()
    tasks = [asyncio.create_task(run_telegram()), asyncio.create_task(run_max())]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
