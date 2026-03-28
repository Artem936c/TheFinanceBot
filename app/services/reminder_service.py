from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.database import SessionFactory
from app.db.models import Reminder
from app.services.user_service import UserService


class ReminderService:
    @staticmethod
    async def set_reminder(platform: str, external_user_id: str, time_raw: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        try:
            reminder_time = datetime.strptime(time_raw.strip(), '%H:%M').time()
        except ValueError:
            return 'Формат времени: /reminder_set 21:00'

        async with SessionFactory() as session:
            result = await session.execute(select(Reminder).where(Reminder.user_id == user_id))
            reminder = result.scalar_one_or_none()
            if reminder:
                reminder.reminder_time = reminder_time
                reminder.is_active = True
            else:
                session.add(Reminder(user_id=user_id, reminder_time=reminder_time, is_active=True))
            await session.commit()

        return f'Напоминание установлено на {reminder_time.strftime("%H:%M")}'

    @staticmethod
    async def disable_reminder(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            result = await session.execute(select(Reminder).where(Reminder.user_id == user_id))
            reminder = result.scalar_one_or_none()
            if not reminder:
                return 'Напоминание не найдено.'
            reminder.is_active = False
            await session.commit()
        return 'Напоминание отключено.'

    @staticmethod
    async def get_due_reminders() -> list[Reminder]:
        now = datetime.now()
        window_start = now - timedelta(minutes=1)
        due: list[Reminder] = []

        async with SessionFactory() as session:
            result = await session.execute(select(Reminder).where(Reminder.is_active.is_(True)))
            reminders = list(result.scalars().all())
            for reminder in reminders:
                scheduled_now = now.replace(
                    hour=reminder.reminder_time.hour,
                    minute=reminder.reminder_time.minute,
                    second=0,
                    microsecond=0,
                )
                if window_start <= scheduled_now <= now:
                    if reminder.last_sent_at and reminder.last_sent_at.date() == now.date() and reminder.last_sent_at.hour == now.hour and reminder.last_sent_at.minute == now.minute:
                        continue
                    reminder.last_sent_at = now
                    due.append(reminder)
            if due:
                await session.commit()
        return due
