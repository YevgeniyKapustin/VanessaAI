from unittest.mock import AsyncMock

import pytest

from app.db.uow import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_uow_commit():
    session = AsyncMock()
    uow = SqlAlchemyUnitOfWork(session)
    await uow.commit()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_uow_rollback():
    session = AsyncMock()
    uow = SqlAlchemyUnitOfWork(session)
    await uow.rollback()
    session.rollback.assert_awaited_once()
