from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession


async def get_turn_session(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
