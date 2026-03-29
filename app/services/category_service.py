from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionFactory
from app.db.models import Category
from app.services.user_service import UserService


class CategoryService:
    TYPE_LABELS = {'income': 'Доход', 'expense': 'Расход'}

    @staticmethod
    def type_label(category_type: str) -> str:
        return CategoryService.TYPE_LABELS.get(category_type, category_type)

    @staticmethod
    async def add_category(platform: str, external_user_id: str, category_type: str, name: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'
        if category_type not in {'income', 'expense'}:
            return 'Тип категории должен быть: доход или расход.'

        async with SessionFactory() as session:
            category = Category(user_id=user_id, type=category_type, name=name.strip())
            session.add(category)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return 'Такая категория уже существует.'
        return f'✅ Категория добавлена: {CategoryService.type_label(category_type)} — {name}'

    @staticmethod
    async def list_categories(platform: str, external_user_id: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            result = await session.execute(
                select(Category).where(Category.user_id == user_id, Category.is_archived.is_(False)).order_by(Category.type, Category.name)
            )
            categories = list(result.scalars().all())

        if not categories:
            return '📂 Категорий пока нет.'

        income = [c for c in categories if c.type == 'income']
        expense = [c for c in categories if c.type == 'expense']
        lines = ['📂 Категории:']
        if income:
            lines.append('\n💚 Доходы:')
            lines.extend([f'- #{c.id} {c.name}' for c in income])
        if expense:
            lines.append('\n💸 Расходы:')
            lines.extend([f'- #{c.id} {c.name}' for c in expense])
        return '\n'.join(lines)

    @staticmethod
    async def delete_category(platform: str, external_user_id: str, category_id: int) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'

        async with SessionFactory() as session:
            result = await session.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id))
            category = result.scalar_one_or_none()
            if not category:
                return 'Категория не найдена.'
            category.is_archived = True
            await session.commit()
        return f'🗑 Категория #{category_id} архивирована.'

    @staticmethod
    async def edit_category(platform: str, external_user_id: str, category_id: int, name: str) -> str:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return 'Сначала выполните /start'
        new_name = (name or '').strip()
        if len(new_name) < 2:
            return 'Название категории должно быть не короче 2 символов.'

        async with SessionFactory() as session:
            result = await session.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id, Category.is_archived.is_(False)))
            category = result.scalar_one_or_none()
            if not category:
                return 'Категория не найдена.'
            category.name = new_name[:255]
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return 'Такая категория уже существует.'
        return f'✏️ Категория #{category_id} переименована в «{new_name}».'

    @staticmethod
    async def find_category_by_name(user_id: int, category_type: str, name: str) -> Category | None:
        async with SessionFactory() as session:
            result = await session.execute(
                select(Category).where(
                    Category.user_id == user_id,
                    Category.type == category_type,
                    Category.name.ilike(name.strip()),
                    Category.is_archived.is_(False),
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def category_exists(platform: str, external_user_id: str, category_id: int) -> bool:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return False
        async with SessionFactory() as session:
            result = await session.execute(select(Category.id).where(Category.id == category_id, Category.user_id == user_id, Category.is_archived.is_(False)))
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def category_buttons(platform: str, external_user_id: str) -> list[list[str]]:
        user_id = await UserService.resolve_user_id(platform, external_user_id)
        if not user_id:
            return []
        async with SessionFactory() as session:
            result = await session.execute(
                select(Category.id).where(Category.user_id == user_id, Category.is_archived.is_(False)).order_by(Category.type, Category.name).limit(12)
            )
            ids = [str(row[0]) for row in result.all()]
        return [ids[i:i + 3] for i in range(0, len(ids), 3)]
