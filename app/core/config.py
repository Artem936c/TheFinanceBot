from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)

    app_name: str = 'FinanceTracker'
    debug: bool = True
    sqlite_path: str = '/app/data/finance_tracker.db'
    timezone: str = 'Europe/Moscow'
    telegram_enabled: bool = True
    max_enabled: bool = True
    telegram_bot_token: str = ''
    max_bot_token: str = ''
    default_currency: str = 'RUB'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
