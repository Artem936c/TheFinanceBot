from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionFactory
from app.db.models import Category, User, UserChannel


DEFAULT_CATEGORIES = {
    'income': ['Зарплата', 'Подработка', 'Возврат'],
    'expense': ['Еда', 'Транспорт', 'Жилье', 'Развлечения'],
}


class UserService:
    @staticmethod
    async def get_or_create_user(
        platform: str,
        external_user_id: str,
        external_chat_id: str,
        username: str | None = None,
    ) -> User:
        async with SessionFactory() as session:
            result = await session.execute(
                select(UserChannel).where(
                    UserChannel.platform == platform,
                    UserChannel.external_user_id == external_user_id,
                )
            )
            channel = result.scalar_one_or_none()
            if channel:
                user_result = await session.execute(select(User).where(User.id == channel.user_id))
                user = user_result.scalar_one()
                if channel.external_chat_id != external_chat_id or channel.username != username:
                    channel.external_chat_id = external_chat_id
                    channel.username = username
                    await session.commit()
                return user

            user = User(name=username)
            session.add(user)
            await session.flush()

            session.add(
                UserChannel(
                    user_id=user.id,
                    platform=platform,
                    external_user_id=external_user_id,
                    external_chat_id=external_chat_id,
                    username=username,
                )
            )
            await session.flush()

            for category_type, names in DEFAULT_CATEGORIES.items():
                for name in names:
                    session.add(Category(user_id=user.id, type=category_type, name=name))

            await session.commit()
            return user

    @staticmethod
    async def resolve_user_id(platform: str, external_user_id: str) -> int | None:
        async with SessionFactory() as session:
            result = await session.execute(
                select(UserChannel.user_id).where(
                    UserChannel.platform == platform,
                    UserChannel.external_user_id == external_user_id,
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_channels_for_user(user_id: int) -> list[UserChannel]:
        async with SessionFactory() as session:
            result = await session.execute(
                select(UserChannel).where(UserChannel.user_id == user_id, UserChannel.is_active.is_(True))
            )
            return list(result.scalars().all())
