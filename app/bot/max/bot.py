from app.core.config import get_settings

settings = get_settings()

try:
    from maxapi import Bot, Dispatcher
except Exception:  # pragma: no cover
    Bot = None
    Dispatcher = None

max_bot = Bot(settings.max_bot_token) if settings.max_bot_token and Bot else None
max_dp = Dispatcher() if Dispatcher else None
