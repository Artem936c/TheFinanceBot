from __future__ import annotations

import logging

from app.bot.max.bot import max_bot
from app.bot.telegram.bot import telegram_bot
from app.db.models import UserChannel

logger = logging.getLogger(__name__)


class ChannelSender:
    @staticmethod
    async def send(channel: UserChannel, text: str) -> None:
        try:
            if channel.platform == 'telegram' and telegram_bot:
                await telegram_bot.send_message(chat_id=channel.external_chat_id, text=text)
                return
            if channel.platform == 'max' and max_bot:
                await max_bot.send_message(chat_id=channel.external_chat_id, text=text)
                return
            logger.warning('Unsupported channel or bot is not configured: %s', channel.platform)
        except Exception as exc:  # pragma: no cover
            logger.exception('Failed to send message to %s: %s', channel.platform, exc)
