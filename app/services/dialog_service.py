from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.bot.common.texts import BACK_TEXT, CONFIRM_TEXT, MAIN_MENU_TEXT, MENU_TEXT, SKIP_TEXT
from app.db.database import SessionFactory
from app.db.models import Category, DialogState, Reminder, Transaction
from app.services.budget_service import BudgetService
from app.services.category_service import CategoryService
from app.services.reminder_service import ReminderService
from app.services.report_service import ReportService
from app.services.transaction_service import TransactionService
from app.services.user_service import UserService
from app.utils.types import BotResponse, IncomingMessage

MAIN_MENU_BUTTONS = [
    ['➕ Доход', '➖ Расход'],
    ['💰 Начальный баланс', '💼 Баланс'],
    ['📅 Сегодня', '🗓 Этот месяц'],
    ['🧾 Последние 5 операций', '📂 Категории'],
    ['➕ Категория', '✏️ Категория', '🗑 Категория'],
    ['💸 Лимит', '⏰ Напоминание'],
    ['✏️ Операцию', '🗑 Операцию'],
]

CATEGORY_PREV_TEXT = '← Категории'
CATEGORY_NEXT_TEXT = 'Категории →'
DATE_TODAY_TEXT = 'Сегодня'
DATE_YESTERDAY_TEXT = 'Вчера'
DATE_CUSTOM_TEXT = 'Другая дата'
REMINDER_DISABLE_TEXT = 'Отключить напоминание'


class DialogService:
    @staticmethod
    async def get_or_create_state(platform: str, external_user_id: str) -> DialogState:
        async with SessionFactory() as session:
            result = await session.execute(
                select(DialogState).where(
                    DialogState.platform == platform,
                    DialogState.external_user_id == external_user_id,
                )
            )
            state = result.scalar_one_or_none()
            if state:
                return state
            state = DialogState(platform=platform, external_user_id=external_user_id)
            session.add(state)
            await session.commit()
            await session.refresh(state)
            return state

    @staticmethod
    async def save_state(platform: str, external_user_id: str, flow: str, step: str, data: dict, history: list[dict]) -> None:
        async with SessionFactory() as session:
            result = await session.execute(
                select(DialogState).where(
                    DialogState.platform == platform,
                    DialogState.external_user_id == external_user_id,
                )
            )
            state = result.scalar_one_or_none()
            if not state:
                state = DialogState(platform=platform, external_user_id=external_user_id)
                session.add(state)
            state.flow = flow
            state.step = step
            state.data_json = json.dumps(data, ensure_ascii=False)
            state.history_json = json.dumps(history, ensure_ascii=False)
            state.updated_at = datetime.utcnow()
            await session.commit()

    @staticmethod
    async def reset_state(platform: str, external_user_id: str) -> None:
        await DialogService.save_state(platform, external_user_id, 'idle', 'idle', {}, [])

    @staticmethod
    async def load(platform: str, external_user_id: str) -> tuple[str, str, dict, list[dict]]:
        state = await DialogService.get_or_create_state(platform, external_user_id)
        return state.flow, state.step, json.loads(state.data_json or '{}'), json.loads(state.history_json or '[]')

    @staticmethod
    def menu_response(text: str = MAIN_MENU_TEXT) -> BotResponse:
        return BotResponse(text=text, buttons=MAIN_MENU_BUTTONS)

    @staticmethod
    async def home_response(platform: str, external_user_id: str, text_prefix: str | None = None) -> BotResponse:
        dashboard = await ReportService.get_dashboard(platform, external_user_id)
        if text_prefix:
            dashboard = f'{text_prefix}\n\n{dashboard}'
        return BotResponse(text=dashboard, buttons=MAIN_MENU_BUTTONS)

    @staticmethod
    def action_response(text: str) -> BotResponse:
        return BotResponse(text=text, buttons=MAIN_MENU_BUTTONS)

    @staticmethod
    def nav_buttons(extra: list[list[str]] | None = None) -> list[list[str]]:
        rows = list(extra or [])
        rows.append([BACK_TEXT, MENU_TEXT])
        return rows

    @staticmethod
    def date_choice_buttons() -> list[list[str]]:
        return DialogService.nav_buttons([[DATE_TODAY_TEXT, DATE_YESTERDAY_TEXT], [DATE_CUSTOM_TEXT]])

    @staticmethod
    def normalize(text: str) -> str:
        return (text or '').strip()

    @staticmethod
    def extract_amount(text: str) -> str | None:
        cleaned = text.replace(' ', '')
        match = re.search(r'[-+]?\d+(?:[\.,]\d+)?', cleaned)
        if not match:
            return None
        value = match.group(0).lstrip('+')
        if value.startswith('-'):
            return None
        return value

    @staticmethod
    def extract_int(text: str) -> int | None:
        match = re.search(r'\d+', text)
        return int(match.group(0)) if match else None

    @staticmethod
    def parse_date(text: str) -> date | None:
        raw = (text or '').strip()
        for fmt in ('%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
        return None

    @staticmethod
    def format_date(value: str | None) -> str:
        if not value:
            return 'не выбрана'
        try:
            return datetime.strptime(value, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            return value

    @staticmethod
    def push(history: list[dict], step: str, data: dict) -> list[dict]:
        items = list(history)
        items.append({'step': step, 'data': dict(data)})
        return items

    @staticmethod
    def is_global_action(text: str) -> bool:
        lowered = DialogService.normalize(text).casefold()
        return lowered in {
            '➕ доход', '+ доход', '➖ расход', '- расход', '💰 начальный баланс', 'начальный баланс',
            '💼 баланс', 'баланс', '📅 сегодня', 'сегодня', '🗓 этот месяц', 'этот месяц',
            '🧾 последние 5 операций', 'последние 5 операций', 'последние операции',
            '📂 категории', 'категории', '➕ категория', 'добавить категорию',
            '✏️ категория', '🗑 категория', '💸 лимит', 'лимит', '⏰ напоминание', 'напоминание',
            '✏️ операцию', 'редактировать', '🗑 операцию', 'удалить',
        }

    @staticmethod
    async def handle(msg: IncomingMessage) -> BotResponse | None:
        text = DialogService.normalize(msg.text)
        lowered = text.casefold()

        if lowered in {'/menu', MENU_TEXT.casefold(), 'меню', 'главное меню'}:
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            user_id = await UserService.resolve_user_id(msg.platform, msg.user_external_id)
            if user_id:
                return await DialogService.home_response(msg.platform, msg.user_external_id)
            return DialogService.menu_response()

        if lowered in {'/start', '/help'}:
            return None

        await UserService.get_or_create_user(
            platform=msg.platform,
            external_user_id=msg.user_external_id,
            external_chat_id=msg.chat_id,
            username=msg.username,
        )
        flow, step, data, history = await DialogService.load(msg.platform, msg.user_external_id)

        if lowered == BACK_TEXT.casefold():
            if not history:
                return await DialogService.home_response(msg.platform, msg.user_external_id, '↩️ Вы уже в главном меню.')
            snapshot = history.pop()
            await DialogService.save_state(msg.platform, msg.user_external_id, flow, snapshot['step'], snapshot['data'], history)
            return await DialogService.render_step(msg.platform, msg.user_external_id, flow, snapshot['step'], snapshot['data'])

        if flow != 'idle' and DialogService.is_global_action(text):
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return await DialogService.start_flow_or_none(msg)

        if flow == 'idle':
            return await DialogService.start_flow_or_none(msg)

        return await DialogService.handle_flow(msg, flow, step, data, history)

    @staticmethod
    async def start_flow_or_none(msg: IncomingMessage) -> BotResponse | None:
        lowered = DialogService.normalize(msg.text).casefold()
        mapping = {
            '/add': ('add_tx', 'type', {}),
            'добавить операцию': ('add_tx', 'type', {}),
            '➕ доход': ('add_tx', 'amount', {'type': 'income', 'type_label': 'Доход', 'category_page': 0}),
            '+ доход': ('add_tx', 'amount', {'type': 'income', 'type_label': 'Доход', 'category_page': 0}),
            '➖ расход': ('add_tx', 'amount', {'type': 'expense', 'type_label': 'Расход', 'category_page': 0}),
            '- расход': ('add_tx', 'amount', {'type': 'expense', 'type_label': 'Расход', 'category_page': 0}),
            '💰 начальный баланс': ('add_tx', 'amount', {'type': 'opening_balance', 'type_label': 'Начальный баланс', 'category_page': 0}),
            'начальный баланс': ('add_tx', 'amount', {'type': 'opening_balance', 'type_label': 'Начальный баланс', 'category_page': 0}),
            '/edit': ('edit_tx', 'choose_id', {}),
            '✏️ операцию': ('edit_tx', 'choose_id', {}),
            'редактировать': ('edit_tx', 'choose_id', {}),
            '/delete': ('delete_tx', 'choose_id', {}),
            '🗑 операцию': ('delete_tx', 'choose_id', {}),
            'удалить': ('delete_tx', 'choose_id', {}),
            '/category_add': ('add_category', 'type', {}),
            '➕ категория': ('add_category', 'type', {}),
            'добавить категорию': ('add_category', 'type', {}),
            '/category_edit': ('edit_category', 'choose_id', {}),
            '✏️ категория': ('edit_category', 'choose_id', {}),
            '/category_delete': ('delete_category', 'choose_id', {}),
            '🗑 категория': ('delete_category', 'choose_id', {}),
            '📂 категории': ('show_categories', 'show', {}),
            'категории': ('show_categories', 'show', {}),
            '/report': ('report', 'period', {}),
            '📅 сегодня': ('report_today', 'show', {}),
            'сегодня': ('report_today', 'show', {}),
            '🗓 этот месяц': ('report_month', 'show', {}),
            'этот месяц': ('report_month', 'show', {}),
            '💼 баланс': ('show_balance', 'show', {}),
            'баланс': ('show_balance', 'show', {}),
            '🧾 последние 5 операций': ('show_operations', 'show', {}),
            'последние 5 операций': ('show_operations', 'show', {}),
            'последние операции': ('show_operations', 'show', {}),
            '💸 лимит': ('limit', 'amount', {}),
            'лимит': ('limit', 'amount', {}),
            '/limit_set': ('limit', 'amount', {}),
            '⏰ напоминание': ('reminder', 'time', {}),
            'напоминание': ('reminder', 'time', {}),
            'напоминания': ('reminder', 'time', {}),
            '/reminder_set': ('reminder', 'time', {}),
        }
        target = mapping.get(lowered)
        if not target:
            return None

        flow, step, initial_data = target
        await DialogService.save_state(msg.platform, msg.user_external_id, flow, step, initial_data, [])

        if flow == 'show_balance':
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return DialogService.action_response(await ReportService.get_balance(msg.platform, msg.user_external_id))
        if flow == 'show_categories':
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return DialogService.action_response(await CategoryService.list_categories(msg.platform, msg.user_external_id))
        if flow == 'show_operations':
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return DialogService.action_response(await TransactionService.list_operations(msg.platform, msg.user_external_id, limit=5))
        if flow == 'report_today':
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return DialogService.action_response(await ReportService.get_period_report(msg.platform, msg.user_external_id, 'day'))
        if flow == 'report_month':
            await DialogService.reset_state(msg.platform, msg.user_external_id)
            return DialogService.action_response(await ReportService.get_period_report(msg.platform, msg.user_external_id, 'month'))

        return await DialogService.render_step(msg.platform, msg.user_external_id, flow, step, initial_data)

    @staticmethod
    async def render_step(platform: str, external_user_id: str, flow: str, step: str, data: dict) -> BotResponse:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return DialogService.menu_response('Сначала выполните /start')

        if flow == 'add_tx':
            if step == 'type':
                return BotResponse('Выберите тип операции.', DialogService.nav_buttons([['Приход', 'Расход'], ['Начальный баланс']]))
            if step == 'amount':
                return BotResponse(f"💵 Введите сумму для операции «{data.get('type_label', 'Операция')}».", DialogService.nav_buttons())
            if step == 'category':
                if data.get('type') not in {'income', 'expense'}:
                    return await DialogService.render_step(platform, external_user_id, flow, 'date_choice', data)
                names = await DialogService.get_category_names(user_id, data['type'])
                if not names:
                    return BotResponse('📂 Категорий этого типа пока нет. Можно пропустить шаг.', DialogService.nav_buttons([[SKIP_TEXT]]))
                page = max(0, int(data.get('category_page', 0)))
                per_page = 6
                total_pages = (len(names) - 1) // per_page + 1
                page = min(page, total_pages - 1)
                current = names[page * per_page:(page + 1) * per_page]
                rows = [[name] for name in current]
                pager = []
                if page > 0:
                    pager.append(CATEGORY_PREV_TEXT)
                if page < total_pages - 1:
                    pager.append(CATEGORY_NEXT_TEXT)
                if pager:
                    rows.append(pager)
                rows.append([SKIP_TEXT])
                type_label = 'дохода' if data.get('type') == 'income' else 'расхода'
                return BotResponse(
                    f'📂 Выберите категорию для {type_label}. Страница {page + 1} из {total_pages}.',
                    DialogService.nav_buttons(rows),
                )
            if step == 'date_choice':
                return BotResponse(f"📅 Выберите дату операции. Сейчас: {DialogService.format_date(data.get('transaction_date'))}.", DialogService.date_choice_buttons())
            if step == 'date_custom':
                return BotResponse('Введите дату в формате ДД.ММ.ГГГГ.', DialogService.nav_buttons())
            if step == 'comment':
                return BotResponse('📝 Введите комментарий к операции или нажмите «Пропустить».', DialogService.nav_buttons([[SKIP_TEXT]]))
            if step == 'confirm':
                lines = [
                    '✅ Проверьте операцию:',
                    f"- Тип: {data.get('type_label')}",
                    f"- Сумма: {data.get('amount')}",
                    f"- Дата: {DialogService.format_date(data.get('transaction_date'))}",
                ]
                if data.get('category_name'):
                    lines.append(f"- Категория: {data.get('category_name')}")
                if data.get('comment'):
                    lines.append(f"- Комментарий: {data.get('comment')}")
                return BotResponse('\n'.join(lines), DialogService.nav_buttons([[CONFIRM_TEXT]]))

        if flow == 'add_category':
            if step == 'type':
                return BotResponse('📂 Для какой группы создать категорию?', DialogService.nav_buttons([['Доход', 'Расход']]))
            if step == 'name':
                return BotResponse('Введите название новой категории.', DialogService.nav_buttons())
            if step == 'confirm':
                return BotResponse(
                    '✅ Проверьте новую категорию:\n'
                    f"- Тип: {data.get('type_label')}\n"
                    f"- Название: {data.get('name')}",
                    DialogService.nav_buttons([[CONFIRM_TEXT]]),
                )

        if flow == 'edit_category':
            if step == 'choose_id':
                return BotResponse(
                    '✏️ Выберите ID категории для редактирования.\n\n' + await CategoryService.list_categories(platform, external_user_id),
                    DialogService.nav_buttons(await DialogService.category_buttons(platform, external_user_id)),
                )
            if step == 'name':
                return BotResponse('✏️ Введите новое название категории.', DialogService.nav_buttons())
            if step == 'confirm':
                return BotResponse(
                    '✅ Проверьте изменения категории:\n'
                    f"- ID: {data.get('category_id')}\n"
                    f"- Новое название: {data.get('name')}",
                    DialogService.nav_buttons([[CONFIRM_TEXT]]),
                )

        if flow == 'delete_category':
            if step == 'choose_id':
                return BotResponse(
                    '🗑 Выберите ID категории для удаления.\n\n' + await CategoryService.list_categories(platform, external_user_id),
                    DialogService.nav_buttons(await DialogService.category_buttons(platform, external_user_id)),
                )
            if step == 'confirm':
                return BotResponse(f"🗑 Удалить категорию #{data.get('category_id')}?", DialogService.nav_buttons([[CONFIRM_TEXT]]))

        if flow == 'report' and step == 'period':
            return BotResponse('📊 Выберите период отчета.', DialogService.nav_buttons([['День', 'Месяц', 'Год']]))

        if flow == 'limit' and step == 'amount':
            current = await ReportService.get_limit_status(platform, external_user_id)
            return BotResponse('💸 Введите новый месячный лимит.\n\n' + current, DialogService.nav_buttons())

        if flow == 'reminder' and step == 'time':
            current = await DialogService.get_reminder_status(platform, external_user_id)
            return BotResponse('⏰ Введите время напоминания в формате ЧЧ:ММ.\n\n' + current, DialogService.nav_buttons([[REMINDER_DISABLE_TEXT]]))

        if flow == 'edit_tx':
            if step == 'choose_id':
                return BotResponse(
                    '✏️ Выберите ID операции для редактирования.\n\n' + await TransactionService.list_operations(platform, external_user_id, limit=5),
                    DialogService.nav_buttons(await DialogService.operation_buttons(platform, external_user_id)),
                )
            if step == 'amount':
                return BotResponse('💵 Введите новую сумму.', DialogService.nav_buttons())
            if step == 'comment':
                return BotResponse('📝 Введите новый комментарий или нажмите «Пропустить».', DialogService.nav_buttons([[SKIP_TEXT]]))
            if step == 'confirm':
                return BotResponse(
                    '✅ Проверьте изменения:\n'
                    f"- ID: {data.get('tx_id')}\n"
                    f"- Сумма: {data.get('amount')}\n"
                    f"- Комментарий: {data.get('comment') or 'без комментария'}",
                    DialogService.nav_buttons([[CONFIRM_TEXT]]),
                )

        if flow == 'delete_tx':
            if step == 'choose_id':
                return BotResponse(
                    '🗑 Выберите ID операции для удаления.\n\n' + await TransactionService.list_operations(platform, external_user_id, limit=5),
                    DialogService.nav_buttons(await DialogService.operation_buttons(platform, external_user_id)),
                )
            if step == 'confirm':
                return BotResponse(f"🗑 Удалить операцию #{data.get('tx_id')}?", DialogService.nav_buttons([[CONFIRM_TEXT]]))

        await DialogService.reset_state(platform, external_user_id)
        return await DialogService.home_response(platform, external_user_id)

    @staticmethod
    async def handle_flow(msg: IncomingMessage, flow: str, step: str, data: dict, history: list[dict]) -> BotResponse:
        text = DialogService.normalize(msg.text)
        lowered = text.casefold()
        platform = msg.platform
        user = msg.user_external_id

        if flow == 'add_tx':
            if step == 'type':
                mapping = {'приход': ('income', 'Доход'), 'расход': ('expense', 'Расход'), 'начальный баланс': ('opening_balance', 'Начальный баланс')}
                if lowered not in mapping:
                    return BotResponse('Выберите тип операции кнопкой или напишите: Приход, Расход, Начальный баланс.', DialogService.nav_buttons([['Приход', 'Расход'], ['Начальный баланс']]))
                tx_type, tx_label = mapping[lowered]
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data.update({'type': tx_type, 'type_label': tx_label, 'category_page': 0})
                await DialogService.save_state(platform, user, flow, 'amount', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'amount', new_data)

            if step == 'amount':
                amount = DialogService.extract_amount(text)
                if not amount:
                    return BotResponse('Не вижу корректной суммы. Пример: 1250.50', DialogService.nav_buttons())
                try:
                    parsed = TransactionService.parse_amount(amount)
                except ValueError as exc:
                    return BotResponse(str(exc), DialogService.nav_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['amount'] = str(parsed)
                next_step = 'date_choice' if new_data.get('type') == 'opening_balance' else 'category'
                await DialogService.save_state(platform, user, flow, next_step, new_data, history)
                return await DialogService.render_step(platform, user, next_step == 'category' and flow or flow, next_step, new_data)

            if step == 'category':
                if lowered in {CATEGORY_NEXT_TEXT.casefold(), CATEGORY_PREV_TEXT.casefold()}:
                    user_id = await UserService.resolve_user_id(platform, user)
                    names = await DialogService.get_category_names(user_id, data['type']) if user_id else []
                    page = int(data.get('category_page', 0))
                    total_pages = max(1, (len(names) - 1) // 6 + 1)
                    page += 1 if lowered == CATEGORY_NEXT_TEXT.casefold() else -1
                    page = max(0, min(total_pages - 1, page))
                    new_data = dict(data)
                    new_data['category_page'] = page
                    await DialogService.save_state(platform, user, flow, step, new_data, history)
                    return await DialogService.render_step(platform, user, flow, step, new_data)
                if lowered == SKIP_TEXT.casefold():
                    category_name = None
                else:
                    user_id = await UserService.resolve_user_id(platform, user)
                    category = await CategoryService.find_category_by_name(user_id, data['type'], text) if user_id else None
                    if not category:
                        return BotResponse('Категория не найдена. Выберите кнопку из списка или нажмите «Пропустить».', DialogService.nav_buttons((await DialogService.render_step(platform, user, flow, step, data)).buttons[:-1]))
                    category_name = category.name
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['category_name'] = category_name
                new_data.pop('category_page', None)
                await DialogService.save_state(platform, user, flow, 'date_choice', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'date_choice', new_data)

            if step == 'date_choice':
                if lowered == DATE_TODAY_TEXT.casefold():
                    selected = date.today()
                elif lowered == DATE_YESTERDAY_TEXT.casefold():
                    selected = date.today() - timedelta(days=1)
                elif lowered == DATE_CUSTOM_TEXT.casefold():
                    history = DialogService.push(history, step, data)
                    await DialogService.save_state(platform, user, flow, 'date_custom', dict(data), history)
                    return await DialogService.render_step(platform, user, flow, 'date_custom', dict(data))
                else:
                    return BotResponse('Выберите дату кнопкой: Сегодня, Вчера или Другая дата.', DialogService.date_choice_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['transaction_date'] = selected.isoformat()
                await DialogService.save_state(platform, user, flow, 'comment', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'comment', new_data)

            if step == 'date_custom':
                parsed_date = DialogService.parse_date(text)
                if not parsed_date:
                    return BotResponse('Некорректная дата. Используйте формат ДД.ММ.ГГГГ.', DialogService.nav_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['transaction_date'] = parsed_date.isoformat()
                await DialogService.save_state(platform, user, flow, 'comment', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'comment', new_data)

            if step == 'comment':
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['comment'] = None if lowered == SKIP_TEXT.casefold() else text[:500]
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)

            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                comment = data.get('comment')
                if data.get('category_name'):
                    comment = f"{data['category_name']} {comment}".strip() if comment else data['category_name']
                tx_date = DialogService.parse_date(DialogService.format_date(data.get('transaction_date')))
                result = await TransactionService.add_transaction(platform, user, data['type'], data['amount'], comment, tx_date=tx_date)
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        if flow == 'add_category':
            if step == 'type':
                mapping = {'доход': ('income', 'Доход'), 'расход': ('expense', 'Расход')}
                if lowered not in mapping:
                    return BotResponse('Выберите тип категории: Доход или Расход.', DialogService.nav_buttons([['Доход', 'Расход']]))
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data.update({'type': mapping[lowered][0], 'type_label': mapping[lowered][1]})
                await DialogService.save_state(platform, user, flow, 'name', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'name', new_data)
            if step == 'name':
                name = text.strip()
                if len(name) < 2:
                    return BotResponse('Название категории должно быть не короче 2 символов.', DialogService.nav_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['name'] = name[:255]
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)
            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                result = await CategoryService.add_category(platform, user, data['type'], data['name'])
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        if flow == 'edit_category':
            if step == 'choose_id':
                category_id = DialogService.extract_int(text)
                if not category_id or not await CategoryService.category_exists(platform, user, category_id):
                    return BotResponse('Категория не найдена. Введите корректный ID из списка.', DialogService.nav_buttons(await DialogService.category_buttons(platform, user)))
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['category_id'] = category_id
                await DialogService.save_state(platform, user, flow, 'name', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'name', new_data)
            if step == 'name':
                name = text.strip()
                if len(name) < 2:
                    return BotResponse('Название категории должно быть не короче 2 символов.', DialogService.nav_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['name'] = name[:255]
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)
            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                result = await CategoryService.edit_category(platform, user, int(data['category_id']), data['name'])
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        if flow == 'delete_category':
            if step == 'choose_id':
                category_id = DialogService.extract_int(text)
                if not category_id or not await CategoryService.category_exists(platform, user, category_id):
                    return BotResponse('Категория не найдена. Введите корректный ID из списка.', DialogService.nav_buttons(await DialogService.category_buttons(platform, user)))
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['category_id'] = category_id
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)
            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                result = await CategoryService.delete_category(platform, user, int(data['category_id']))
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        if flow == 'report' and step == 'period':
            mapping = {'день': 'day', 'месяц': 'month', 'год': 'year'}
            period = mapping.get(lowered)
            if not period:
                return BotResponse('Выберите период: День, Месяц или Год.', DialogService.nav_buttons([['День', 'Месяц', 'Год']]))
            result = await ReportService.get_period_report(platform, user, period)
            await DialogService.reset_state(platform, user)
            return DialogService.action_response(result)

        if flow == 'limit' and step == 'amount':
            amount = DialogService.extract_amount(text)
            if not amount:
                return BotResponse('Не вижу корректной суммы лимита. Пример: 50000', DialogService.nav_buttons())
            result = await BudgetService.set_limit(platform, user, amount)
            await DialogService.reset_state(platform, user)
            return DialogService.action_response(result)

        if flow == 'reminder' and step == 'time':
            if lowered == REMINDER_DISABLE_TEXT.casefold():
                result = await ReminderService.disable_reminder(platform, user)
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)
            try:
                datetime.strptime(text, '%H:%M')
            except ValueError:
                return BotResponse('Некорректное время. Пример: 21:00', DialogService.nav_buttons([[REMINDER_DISABLE_TEXT]]))
            result = await ReminderService.set_reminder(platform, user, text)
            await DialogService.reset_state(platform, user)
            return DialogService.action_response(result)

        if flow == 'edit_tx':
            if step == 'choose_id':
                tx_id = DialogService.extract_int(text)
                if not tx_id or not await DialogService.operation_exists(platform, user, tx_id):
                    return BotResponse('Операция не найдена. Введите корректный ID из списка.', DialogService.nav_buttons(await DialogService.operation_buttons(platform, user)))
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['tx_id'] = tx_id
                await DialogService.save_state(platform, user, flow, 'amount', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'amount', new_data)
            if step == 'amount':
                amount = DialogService.extract_amount(text)
                if not amount:
                    return BotResponse('Не вижу корректной суммы. Пример: 999.99', DialogService.nav_buttons())
                try:
                    parsed = TransactionService.parse_amount(amount)
                except ValueError as exc:
                    return BotResponse(str(exc), DialogService.nav_buttons())
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['amount'] = str(parsed)
                await DialogService.save_state(platform, user, flow, 'comment', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'comment', new_data)
            if step == 'comment':
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['comment'] = None if lowered == SKIP_TEXT.casefold() else text[:500]
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)
            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                result = await TransactionService.edit_transaction(platform, user, int(data['tx_id']), data['amount'], data.get('comment'))
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        if flow == 'delete_tx':
            if step == 'choose_id':
                tx_id = DialogService.extract_int(text)
                if not tx_id or not await DialogService.operation_exists(platform, user, tx_id):
                    return BotResponse('Операция не найдена. Введите корректный ID из списка.', DialogService.nav_buttons(await DialogService.operation_buttons(platform, user)))
                history = DialogService.push(history, step, data)
                new_data = dict(data)
                new_data['tx_id'] = tx_id
                await DialogService.save_state(platform, user, flow, 'confirm', new_data, history)
                return await DialogService.render_step(platform, user, flow, 'confirm', new_data)
            if step == 'confirm':
                if lowered != CONFIRM_TEXT.casefold():
                    return BotResponse('Нажмите «Подтвердить» или вернитесь назад.', DialogService.nav_buttons([[CONFIRM_TEXT]]))
                result = await TransactionService.delete_transaction(platform, user, int(data['tx_id']))
                await DialogService.reset_state(platform, user)
                return DialogService.action_response(result)

        await DialogService.reset_state(platform, user)
        return DialogService.action_response('⚠️ Сценарий сброшен. Выберите действие заново.')

    @staticmethod
    async def get_category_names(user_id: int, category_type: str) -> list[str]:
        async with SessionFactory() as session:
            result = await session.execute(
                select(Category.name).where(
                    Category.user_id == user_id,
                    Category.type == category_type,
                    Category.is_archived.is_(False),
                ).order_by(Category.name)
            )
            return [row[0] for row in result.all()]

    @staticmethod
    async def operation_exists(platform: str, external_user_id: str, tx_id: int) -> bool:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return False
        async with SessionFactory() as session:
            result = await session.execute(select(Transaction.id).where(Transaction.id == tx_id, Transaction.user_id == user_id))
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def operation_buttons(platform: str, external_user_id: str) -> list[list[str]]:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return []
        async with SessionFactory() as session:
            result = await session.execute(select(Transaction.id).where(Transaction.user_id == user_id).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(5))
            ids = [str(row[0]) for row in result.all()]
        return [ids[i:i + 3] for i in range(0, len(ids), 3)]

    @staticmethod
    async def category_buttons(platform: str, external_user_id: str) -> list[list[str]]:
        return await CategoryService.category_buttons(platform, external_user_id)

    @staticmethod
    async def get_reminder_status(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Напоминание недоступно.'
        async with SessionFactory() as session:
            result = await session.execute(select(Reminder).where(Reminder.user_id == user_id))
            reminder = result.scalar_one_or_none()
        if not reminder:
            return 'Напоминание пока не установлено.'
        status = 'включено' if reminder.is_active else 'отключено'
        return f'Текущее напоминание: {reminder.reminder_time.strftime("%H:%M")} ({status})'
