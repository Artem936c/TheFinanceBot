from __future__ import annotations

from app.bot.common.texts import HELP_TEXT
from app.services.budget_service import BudgetService
from app.services.category_service import CategoryService
from app.services.dialog_service import DialogService
from app.services.reminder_service import ReminderService
from app.services.report_service import ReportService
from app.services.transaction_service import TransactionService
from app.services.user_service import UserService
from app.utils.types import BotResponse, IncomingMessage


class CommandRouter:
    async def handle(self, msg: IncomingMessage) -> BotResponse:
        text = (msg.text or '').strip()
        if not text:
            return BotResponse('Пустое сообщение. Используйте /help')

        dialog_response = await DialogService.handle(msg)
        if dialog_response is not None:
            return dialog_response

        if text.startswith('/start'):
            await UserService.get_or_create_user(
                platform=msg.platform,
                external_user_id=msg.user_external_id,
                external_chat_id=msg.chat_id,
                username=msg.username,
            )
            return await DialogService.home_response(
                msg.platform,
                msg.user_external_id,
                '👋 Привет! Я FinanceTracker.\nПомогу учитывать доходы и расходы в Telegram и MAX.'
            )

        if text.startswith('/help'):
            return BotResponse(HELP_TEXT, buttons=DialogService.menu_response().buttons)

        user_id = await UserService.resolve_user_id(msg.platform, msg.user_external_id)
        if not user_id:
            return BotResponse('Сначала выполните /start')

        if text.startswith('/balance'):
            return DialogService.action_response(await ReportService.get_balance(msg.platform, msg.user_external_id))

        if text.startswith('/report'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return await DialogService.start_flow_or_none(
                    IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/report', msg.username, msg.message_id)
                ) or BotResponse('Используйте: /report day|month|year')
            return DialogService.action_response(await ReportService.get_period_report(msg.platform, msg.user_external_id, parts[1].strip()))

        if text.startswith('/operations'):
            return DialogService.action_response(await TransactionService.list_operations(msg.platform, msg.user_external_id))

        if text.startswith('/income'):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                return BotResponse('Используйте: /income 2500 Зарплата')
            amount = parts[1]
            comment = parts[2] if len(parts) > 2 else None
            return DialogService.action_response(await TransactionService.add_transaction(msg.platform, msg.user_external_id, 'income', amount, comment))

        if text.startswith('/expense'):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                return BotResponse('Используйте: /expense 430 Такси')
            amount = parts[1]
            comment = parts[2] if len(parts) > 2 else None
            return DialogService.action_response(await TransactionService.add_transaction(msg.platform, msg.user_external_id, 'expense', amount, comment))

        if text.startswith('/opening'):
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                return BotResponse('Используйте: /opening 10000 Начальный баланс')
            amount = parts[1]
            comment = parts[2] if len(parts) > 2 else None
            return DialogService.action_response(await TransactionService.add_transaction(msg.platform, msg.user_external_id, 'opening_balance', amount, comment))

        if text.startswith('/edit'):
            parts = text.split(maxsplit=3)
            if len(parts) < 3:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/edit', msg.username, msg.message_id)) or BotResponse('Используйте: /edit 12 499.99 Новый комментарий')
            tx_id = int(parts[1])
            amount = parts[2]
            comment = parts[3] if len(parts) > 3 else None
            return DialogService.action_response(await TransactionService.edit_transaction(msg.platform, msg.user_external_id, tx_id, amount, comment))

        if text.startswith('/delete'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/delete', msg.username, msg.message_id)) or BotResponse('Используйте: /delete 12')
            return DialogService.action_response(await TransactionService.delete_transaction(msg.platform, msg.user_external_id, int(parts[1])))

        if text.startswith('/category_add'):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/category_add', msg.username, msg.message_id)) or BotResponse('Используйте: /category_add expense Еда')
            return DialogService.action_response(await CategoryService.add_category(msg.platform, msg.user_external_id, parts[1].strip(), parts[2].strip()))

        if text.startswith('/category_edit'):
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/category_edit', msg.username, msg.message_id)) or BotResponse('Используйте: /category_edit 3 Продукты')
            return DialogService.action_response(await CategoryService.edit_category(msg.platform, msg.user_external_id, int(parts[1]), parts[2].strip()))

        if text.startswith('/categories'):
            return DialogService.action_response(await CategoryService.list_categories(msg.platform, msg.user_external_id))

        if text.startswith('/category_delete'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/category_delete', msg.username, msg.message_id)) or BotResponse('Используйте: /category_delete 3')
            return DialogService.action_response(await CategoryService.delete_category(msg.platform, msg.user_external_id, int(parts[1])))

        if text.startswith('/limit_set'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/limit_set', msg.username, msg.message_id)) or BotResponse('Используйте: /limit_set 50000')
            return DialogService.action_response(await BudgetService.set_limit(msg.platform, msg.user_external_id, parts[1]))

        if text.startswith('/limit_status'):
            return DialogService.action_response(await ReportService.get_limit_status(msg.platform, msg.user_external_id))

        if text.startswith('/reminder_set'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return await DialogService.start_flow_or_none(IncomingMessage(msg.platform, msg.user_external_id, msg.chat_id, '/reminder_set', msg.username, msg.message_id)) or BotResponse('Используйте: /reminder_set 21:00')
            return DialogService.action_response(await ReminderService.set_reminder(msg.platform, msg.user_external_id, parts[1]))

        if text.startswith('/reminder_off'):
            return DialogService.action_response(await ReminderService.disable_reminder(msg.platform, msg.user_external_id))

        return DialogService.menu_response('Неизвестная команда. Используйте кнопки меню или /help')


router = CommandRouter()
