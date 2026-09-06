from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vanessa.infrastructure.db.models import User


def _fill_blank(user: User, field: str, incoming: str | None) -> bool:
    if not incoming or getattr(user, field):
        return False
    setattr(user, field, incoming)
    return True


def _fill_missing_names(
    user: User,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    nickname: str | None,
) -> None:
    _fill_blank(user, "username", username)
    _fill_blank(user, "first_name", first_name)
    _fill_blank(user, "last_name", last_name)
    _fill_blank(user, "nickname", nickname)


def _assign_nickname(user: User, nickname: str | None, *, force_nickname: bool) -> bool:
    if not nickname:
        return False
    if not force_nickname and user.nickname:
        return False
    if user.nickname == nickname:
        return False
    user.nickname = nickname
    return True


def _apply_profile_fields(
    user: User,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    nickname: str | None,
    *,
    force_nickname: bool,
) -> bool:
    username_changed = _fill_blank(user, "username", username)
    first_changed = _fill_blank(user, "first_name", first_name)
    last_changed = _fill_blank(user, "last_name", last_name)
    nick_changed = _assign_nickname(user, nickname, force_nickname=force_nickname)
    return username_changed or first_changed or last_changed or nick_changed


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
    ) -> User:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            _fill_missing_names(user, username, first_name, last_name, nickname)
            await self._session.flush()
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
        force_nickname: bool = False,
    ) -> tuple[User, str]:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                nickname=nickname,
            )
            self._session.add(user)
            await self._session.flush()
            return user, "created"

        changed = _apply_profile_fields(
            user,
            username,
            first_name,
            last_name,
            nickname,
            force_nickname=force_nickname,
        )
        if changed:
            await self._session.flush()
            return user, "updated"
        return user, "unchanged"
