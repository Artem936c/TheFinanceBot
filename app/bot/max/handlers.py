from __future__ import annotations

from app.bot.common.router import router as command_router
from app.bot.max.bot import max_dp
from app.utils.types import IncomingMessage

try:
    from maxapi.types import ButtonsPayload, MessageButton
except Exception:  # pragma: no cover
    ButtonsPayload = None
    MessageButton = None


def _build_max_attachments(buttons: list[list[str]]):
    if not buttons or not ButtonsPayload or not MessageButton:
        return None
    payload_buttons = []
    for row in buttons:
        payload_buttons.append([MessageButton(text=text) for text in row])
    return [ButtonsPayload(buttons=payload_buttons).pack()]


if max_dp:
    from maxapi.types import MessageCreated

    @max_dp.message_created()
    async def handle_max_message(event: MessageCreated):
        text = getattr(getattr(event.message, 'body', None), 'text', '') or ''
        if not text:
            await event.message.answer('Поддерживаются текстовые команды. Используйте /help')
            return

        response = await command_router.handle(
            IncomingMessage(
                platform='max',
                user_external_id=str(getattr(event, 'user_id', '')),
                chat_id=str(getattr(event, 'chat_id', '')),
                text=text,
                username=None,
                message_id=str(getattr(event.message, 'message_id', '')),
            )
        )
        attachments = _build_max_attachments(response.buttons)
        if attachments:
            await event.message.answer(response.text, attachments=attachments)
        else:
            await event.message.answer(response.text)
