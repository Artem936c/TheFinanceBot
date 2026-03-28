from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select

from app.db.database import SessionFactory
from app.db.models import Category, Transaction
from app.services.user_service import UserService


class TransactionService:
    @staticmethod
    def parse_amount(value: str) -> Decimal:
        try:
            normalized = value.replace(',', '.').strip()
            amount = Decimal(normalized)
        except InvalidOperation as exc:
            raise ValueError('Некорректная сумма.') from exc
        if amount <= 0:
            raise ValueError('Сумма должна быть больше нуля.')
        return amount.quantize(Decimal('0.01'))

    @staticmethod
    async def add_transaction(
        platform: str,
        external_user_id: str,
        tx_type: str,
        amount_raw: str,
        comment: str | None = None,
        tx_date: date | None = None,
    ) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        try:
            amount = TransactionService.parse_amount(amount_raw)
        except ValueError as exc:
            return str(exc)
        comment = (comment or '').strip() or None
        category_id = None

        async with SessionFactory() as session:
            if comment and tx_type in {'income', 'expense'}:
                first_word = comment.split()[0]
                category_result = await session.execute(
                    select(Category).where(
                        Category.user_id == user_id,
                        Category.type == tx_type,
                        Category.name.ilike(first_word),
                        Category.is_archived.is_(False),
                    )
                )
                category = category_result.scalar_one_or_none()
                if category:
                    category_id = category.id

            tx = Transaction(
                user_id=user_id,
                category_id=category_id,
                type=tx_type,
                amount=amount,
                comment=comment,
                transaction_date=tx_date or date.today(),
            )
            session.add(tx)
            await session.commit()
            sign = '+' if tx_type in {'income', 'opening_balance'} else '-'
            return f'Операция сохранена: #{tx.id} {sign}{amount} за {tx.transaction_date.strftime("%d.%m.%Y")}.'

    @staticmethod
    async def list_operations(platform: str, external_user_id: str, limit: int = 10) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(limit)
            )
            transactions = list(result.scalars().all())

        if not transactions:
            return 'Операций пока нет.'

        lines = ['Последние операции:']
        for tx in transactions:
            sign = '+' if tx.type in {'income', 'opening_balance'} else '-'
            lines.append(f"- #{tx.id} {tx.transaction_date.strftime('%d.%m.%Y')} {sign}{tx.amount} [{tx.type}] {tx.comment or ''}".rstrip())
        return '\n'.join(lines)

    @staticmethod
    async def edit_transaction(platform: str, external_user_id: str, tx_id: int, amount_raw: str, comment: str | None) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'
        try:
            amount = TransactionService.parse_amount(amount_raw)
        except ValueError as exc:
            return str(exc)

        async with SessionFactory() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id)
            )
            tx = result.scalar_one_or_none()
            if not tx:
                return 'Операция не найдена.'
            tx.amount = amount
            tx.comment = (comment or '').strip() or None
            await session.commit()
        return f'Операция #{tx_id} обновлена.'

    @staticmethod
    async def delete_transaction(platform: str, external_user_id: str, tx_id: int) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            result = await session.execute(
                delete(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id)
            )
            await session.commit()
            if result.rowcount == 0:
                return 'Операция не найдена.'
        return f'Операция #{tx_id} удалена.'
