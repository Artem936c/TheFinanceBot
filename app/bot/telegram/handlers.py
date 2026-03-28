from aiogram import Router
from aiogram.types import Message

from app.bot.common.router import router as command_router
from app.bot.telegram.keyboards import build_reply_keyboard
from app.utils.types import IncomingMessage

telegram_router = Router()


@telegram_router.message()
async def handle_telegram_message(message: Message) -> None:
    if not message.text:
        await message.answer('Поддерживаются текстовые команды. Используйте /help')
        return

    response = await command_router.handle(
        IncomingMessage(
            platform='telegram',
            user_external_id=str(message.from_user.id),
            chat_id=str(message.chat.id),
            text=message.text,
            username=message.from_user.username,
            message_id=str(message.message_id),
        )
    )
    await message.answer(
        response.text,
        reply_markup=build_reply_keyboard(response.buttons, remove=response.remove_keyboard),
    )
