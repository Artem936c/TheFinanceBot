from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select

from app.db.database import SessionFactory
from app.db.models import BudgetLimit, Transaction
from app.services.user_service import UserService


class ReportService:

    @staticmethod
    async def get_dashboard(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        today = date.today()
        month_start = today.replace(day=1)

        async with SessionFactory() as session:
            balance_stmt = select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.type.in_(['income', 'opening_balance']), Transaction.amount),
                            else_=-Transaction.amount,
                        )
                    ),
                    0,
                )
            ).where(Transaction.user_id == user_id)
            balance = Decimal((await session.execute(balance_stmt)).scalar_one() or 0).quantize(Decimal('0.01'))

            today_stmt = select(
                func.coalesce(func.sum(case((Transaction.type == 'income', Transaction.amount), else_=0)), 0),
                func.coalesce(func.sum(case((Transaction.type == 'opening_balance', Transaction.amount), else_=0)), 0),
                func.coalesce(func.sum(case((Transaction.type == 'expense', Transaction.amount), else_=0)), 0),
            ).where(
                Transaction.user_id == user_id,
                Transaction.transaction_date == today,
            )
            today_income, today_opening, today_expense = (await session.execute(today_stmt)).one()

            month_expense_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id,
                Transaction.type == 'expense',
                Transaction.transaction_date >= month_start,
                Transaction.transaction_date <= today,
            )
            month_expense = Decimal((await session.execute(month_expense_stmt)).scalar_one() or 0).quantize(Decimal('0.01'))

            recent_stmt = select(Transaction).where(Transaction.user_id == user_id).order_by(
                Transaction.transaction_date.desc(), Transaction.id.desc()
            ).limit(5)
            recent = list((await session.execute(recent_stmt)).scalars().all())

        today_net = (Decimal(today_income or 0) + Decimal(today_opening or 0) - Decimal(today_expense or 0)).quantize(Decimal('0.01'))
        lines = [
            'FinanceTracker',
            '',
            f'Баланс: {balance}',
            f'Сегодня: {today_net}',
            f'Расходы за месяц: {month_expense}',
            '',
            'Последние 5 операций:',
        ]
        if recent:
            for tx in recent:
                sign = '+' if tx.type in {'income', 'opening_balance'} else '-'
                lines.append(f'• #{tx.id} {tx.transaction_date.strftime("%d.%m")} {sign}{tx.amount} {tx.comment or ""}'.rstrip())
        else:
            lines.append('• Пока нет операций.')
        lines.append('')
        lines.append('Выберите действие кнопкой ниже.')
        return '\n'.join(lines)

    @staticmethod
    async def get_balance(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            stmt = select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.type.in_(['income', 'opening_balance']), Transaction.amount),
                            else_=-Transaction.amount,
                        )
                    ),
                    0,
                )
            ).where(Transaction.user_id == user_id)
            result = await session.execute(stmt)
            balance = Decimal(result.scalar_one() or 0).quantize(Decimal('0.01'))
        return f'Текущий баланс: {balance}'

    @staticmethod
    async def get_period_report(platform: str, external_user_id: str, period: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        today = date.today()
        if period == 'day':
            start_date = end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today.replace(day=monthrange(today.year, today.month)[1])
        elif period == 'year':
            start_date = date(today.year, 1, 1)
            end_date = date(today.year, 12, 31)
        else:
            return 'Используйте: /report day|month|year'

        async with SessionFactory() as session:
            stmt = select(
                func.coalesce(
                    func.sum(case((Transaction.type == 'income', Transaction.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Transaction.type == 'opening_balance', Transaction.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Transaction.type == 'expense', Transaction.amount), else_=0)),
                    0,
                ),
            ).where(
                Transaction.user_id == user_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
            result = await session.execute(stmt)
            income, opening, expense = result.one()
            income = Decimal(income or 0)
            opening = Decimal(opening or 0)
            expense = Decimal(expense or 0)
            net = income + opening - expense

        return (
            f'Отчет за {period}:\n'
            f'- Период: {start_date.isoformat()} .. {end_date.isoformat()}\n'
            f'- Доходы: {income.quantize(Decimal("0.01"))}\n'
            f'- Начальный баланс: {opening.quantize(Decimal("0.01"))}\n'
            f'- Расходы: {expense.quantize(Decimal("0.01"))}\n'
            f'- Итог: {net.quantize(Decimal("0.01"))}'
        )

    @staticmethod
    async def get_limit_status(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        today = date.today()
        month_start = today.replace(day=1)
        month_end = today.replace(day=monthrange(today.year, today.month)[1])

        async with SessionFactory() as session:
            limit_result = await session.execute(select(BudgetLimit).where(BudgetLimit.user_id == user_id))
            limit = limit_result.scalar_one_or_none()
            if not limit:
                return 'Лимит не установлен. Используйте /limit_set 50000'

            expense_stmt = select(
                func.coalesce(func.sum(Transaction.amount), 0)
            ).where(
                Transaction.user_id == user_id,
                Transaction.type == 'expense',
                Transaction.transaction_date >= month_start,
                Transaction.transaction_date <= month_end,
            )
            expense_result = await session.execute(expense_stmt)
            spent = Decimal(expense_result.scalar_one() or 0).quantize(Decimal('0.01'))
            limit_value = Decimal(limit.monthly_limit).quantize(Decimal('0.01'))
            left = (limit_value - spent).quantize(Decimal('0.01'))
            percent = Decimal('0.00') if limit_value == 0 else ((spent / limit_value) * 100).quantize(Decimal('0.01'))

        return (
            'Статус лимита за текущий месяц:\n'
            f'- Лимит: {limit_value}\n'
            f'- Потрачено: {spent}\n'
            f'- Осталось: {left}\n'
            f'- Использовано: {percent}%'
        )
