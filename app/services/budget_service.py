from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.db.database import SessionFactory
from app.db.models import BudgetLimit
from app.services.transaction_service import TransactionService
from app.services.user_service import UserService


class BudgetService:
    @staticmethod
    async def set_limit(platform: str, external_user_id: str, amount_raw: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'
        try:
            amount = TransactionService.parse_amount(amount_raw)
        except ValueError as exc:
            return str(exc)

        async with SessionFactory() as session:
            result = await session.execute(select(BudgetLimit).where(BudgetLimit.user_id == user_id))
            limit = result.scalar_one_or_none()
            if limit:
                limit.monthly_limit = Decimal(amount)
            else:
                session.add(BudgetLimit(user_id=user_id, monthly_limit=Decimal(amount)))
            await session.commit()
        return f'Лимит на месяц установлен: {amount}'
