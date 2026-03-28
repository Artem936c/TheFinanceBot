from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.channel_sender import ChannelSender
from app.services.reminder_service import ReminderService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def process_reminders() -> None:
    due_reminders = await ReminderService.get_due_reminders()
    for reminder in due_reminders:
        channels = await UserService.get_channels_for_user(reminder.user_id)
        for channel in channels:
            await ChannelSender.send(channel, 'Напоминание FinanceTracker: не забудьте внести сегодняшние операции.')


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(process_reminders, 'interval', minutes=1, id='finance_tracker_reminders', replace_existing=True)
    scheduler.start()
    logger.info('Scheduler started')
