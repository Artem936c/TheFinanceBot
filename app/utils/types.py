from dataclasses import dataclass, field
from typing import Literal

Platform = Literal['telegram', 'max']


@dataclass(slots=True)
class IncomingMessage:
    platform: Platform
    user_external_id: str
    chat_id: str
    text: str
    username: str | None = None
    message_id: str | None = None


@dataclass(slots=True)
class BotResponse:
    text: str
    buttons: list[list[str]] = field(default_factory=list)
    remove_keyboard: bool = False
