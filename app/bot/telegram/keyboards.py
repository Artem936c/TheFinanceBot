from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.bot.common.texts import BACK_TEXT, MENU_TEXT


def build_reply_keyboard(buttons: list[list[str]] | None = None, remove: bool = False):
    if remove:
        return ReplyKeyboardRemove()
    rows = buttons or []
    if not rows:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder='Выберите действие',
    )


def with_navigation(buttons: list[list[str]] | None = None) -> list[list[str]]:
    rows = list(buttons or [])
    rows.append([BACK_TEXT, MENU_TEXT])
    return rows
