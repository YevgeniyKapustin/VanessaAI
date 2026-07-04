from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.messages import RAG_SOURCE_ROLE, StoredMessage
from app.db.models import Message, User
from app.db.repository import MessageRepository, UserRepository


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _mappings_result(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    return result


@pytest.mark.asyncio
async def test_user_get_or_create_returns_existing():
    session = AsyncMock()
    user = User(id=1, telegram_id=42)
    session.execute = AsyncMock(return_value=_scalar_result(user))
    repo = UserRepository(session)
    result = await repo.get_or_create(42, username="new", first_name="Ann")
    assert result.username == "new"
    assert result.first_name == "Ann"
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_user_get_or_create_inserts_new_user():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalar_result(None))

    async def flush() -> None:
        for obj in session.add.call_args_list:
            added = obj.args[0]
            if isinstance(added, User):
                added.id = 7

    session.flush = AsyncMock(side_effect=flush)
    repo = UserRepository(session)
    user = await repo.get_or_create(99, first_name="Ann", nickname="A")
    assert user.telegram_id == 99
    assert user.nickname == "A"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_user_upsert_profile_force_nickname():
    session = AsyncMock()
    user = User(id=1, telegram_id=5, nickname="old")
    session.execute = AsyncMock(return_value=_scalar_result(user))
    repo = UserRepository(session)
    updated, change = await repo.upsert_profile(
        5,
        nickname="new",
        force_nickname=True,
    )
    assert updated.nickname == "new"
    assert change == "updated"


@pytest.mark.asyncio
async def test_message_create_assigns_id_and_updates_fts():
    session = AsyncMock()
    session.execute = AsyncMock()

    async def flush() -> None:
        for call in session.add.call_args_list:
            message = call.args[0]
            if isinstance(message, Message):
                message.id = 10

    session.flush = AsyncMock(side_effect=flush)
    repo = MessageRepository(session)
    stored = await repo.create(
        role=RAG_SOURCE_ROLE,
        content="привет",
        sender_telegram_id=1,
    )
    assert stored.id == 10
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_message_get_existing_ids_empty():
    session = AsyncMock()
    repo = MessageRepository(session)
    assert await repo.get_existing_telegram_message_ids([]) == set()


@pytest.mark.asyncio
async def test_message_get_by_ids_preserves_order():
    session = AsyncMock()
    first = Message(id=1, role="user", content="a")
    second = Message(id=2, role="user", content="b")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [second, first]
    session.execute = AsyncMock(return_value=result)
    repo = MessageRepository(session)
    ordered = await repo.get_by_ids([1, 2])
    assert [item.id for item in ordered] == [1, 2]


@pytest.mark.asyncio
async def test_message_update_qdrant_point_id_noop_when_missing():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    repo = MessageRepository(session)
    await repo.update_qdrant_point_id(1, "pt-1")
    session.get.assert_awaited_once_with(Message, 1)


@pytest.mark.asyncio
async def test_user_get_by_telegram_id():
    session = AsyncMock()
    user = User(id=1, telegram_id=42)
    session.execute = AsyncMock(return_value=_scalar_result(user))
    repo = UserRepository(session)
    assert await repo.get_by_telegram_id(42) is user


@pytest.mark.asyncio
async def test_user_upsert_profile_creates_new():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalar_result(None))

    async def flush() -> None:
        for call in session.add.call_args_list:
            added = call.args[0]
            if isinstance(added, User):
                added.id = 3

    session.flush = AsyncMock(side_effect=flush)
    repo = UserRepository(session)
    user, change = await repo.upsert_profile(7, username="u")
    assert change == "created"
    assert user.telegram_id == 7


@pytest.mark.asyncio
async def test_user_upsert_profile_unchanged():
    session = AsyncMock()
    user = User(id=1, telegram_id=5, username="same", nickname="nick")
    session.execute = AsyncMock(return_value=_scalar_result(user))
    repo = UserRepository(session)
    updated, change = await repo.upsert_profile(5, username="same", nickname="nick")
    assert change == "unchanged"
    assert updated is user
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_upsert_profile_fills_empty_fields():
    session = AsyncMock()
    user = User(id=1, telegram_id=5)
    session.execute = AsyncMock(return_value=_scalar_result(user))
    repo = UserRepository(session)
    updated, change = await repo.upsert_profile(
        5,
        username="u",
        first_name="A",
        last_name="B",
    )
    assert change == "updated"
    assert updated.username == "u"
    assert updated.first_name == "A"
    assert updated.last_name == "B"


@pytest.mark.asyncio
async def test_message_get_existing_ids():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_rows_result([(10,), (None,), (20,)]))
    repo = MessageRepository(session)
    assert await repo.get_existing_telegram_message_ids([10, 20]) == {10, 20}


@pytest.mark.asyncio
async def test_message_get_by_id():
    session = AsyncMock()
    message = Message(id=5, role="user", content="x")
    session.execute = AsyncMock(return_value=_scalar_result(message))
    repo = MessageRepository(session)
    stored = await repo.get_by_id(5)
    assert stored is not None
    assert stored.id == 5


@pytest.mark.asyncio
async def test_message_get_by_id_missing():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalar_result(None))
    repo = MessageRepository(session)
    assert await repo.get_by_id(5) is None


@pytest.mark.asyncio
async def test_message_get_distinct_sender_ids():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_rows_result([(1,), (2,)]))
    repo = MessageRepository(session)
    assert await repo.get_distinct_sender_telegram_ids() == [1, 2]


@pytest.mark.asyncio
async def test_message_fulltext_search():
    session = AsyncMock()
    row = {
        "id": 1,
        "sender_telegram_id": 2,
        "telegram_message_id": 3,
        "role": "user",
        "content": "привет",
        "qdrant_point_id": None,
        "created_at": datetime.now(timezone.utc),
    }
    session.execute = AsyncMock(return_value=_mappings_result([row]))
    repo = MessageRepository(session)
    hits = await repo.fulltext_search("привет", limit=5)
    assert len(hits) == 1
    assert hits[0].content == "привет"


@pytest.mark.asyncio
async def test_message_get_recent():
    session = AsyncMock()
    row = {
        "id": 1,
        "sender_telegram_id": 2,
        "telegram_message_id": 3,
        "role": "user",
        "content": "recent",
        "qdrant_point_id": None,
        "created_at": datetime.now(timezone.utc),
        "sender_name": "Ann",
    }
    session.execute = AsyncMock(return_value=_mappings_result([row]))
    repo = MessageRepository(session)
    recent = await repo.get_recent(limit=1)
    assert len(recent) == 1
    assert recent[0].sender_name == "Ann"


@pytest.mark.asyncio
async def test_message_window_blocks_without_context():
    session = AsyncMock()
    first = Message(id=1, role="user", content="a")
    second = Message(id=2, role="assistant", content="b")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second]
    session.execute = AsyncMock(return_value=result)
    repo = MessageRepository(session)
    blocks = await repo.get_conversation_window_blocks([1, 2], before=0, after=0)
    assert blocks[0][0] == 1
    assert blocks[0][1][0].id == 1
    assert blocks[0][1][0].role == "user"


@pytest.mark.asyncio
async def test_message_update_qdrant_point_id_updates():
    session = AsyncMock()
    message = Message(id=1, role="user", content="x")
    session.get = AsyncMock(return_value=message)
    repo = MessageRepository(session)
    await repo.update_qdrant_point_id(1, "pt-99")
    assert message.qdrant_point_id == "pt-99"


def _window_row(msg_id: int, content: str) -> dict:
    return {
        "id": msg_id,
        "sender_telegram_id": 1,
        "telegram_message_id": msg_id,
        "role": "user",
        "content": content,
        "qdrant_point_id": None,
        "created_at": datetime.now(timezone.utc),
        "sender_name": "user",
    }


@pytest.mark.asyncio
async def test_window_for_anchor_returns_empty_when_missing():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalar_result(None))
    repo = MessageRepository(session)
    assert await repo._window_for_anchor(99, before=1, after=1) == []


@pytest.mark.asyncio
async def test_window_for_anchor_builds_before_center_after():
    session = AsyncMock()
    repo = MessageRepository(session)
    created = datetime.now(timezone.utc)
    anchor = StoredMessage(
        id=10,
        role="user",
        content="center",
        created_at=created,
    )
    repo.get_by_id = AsyncMock(return_value=anchor)

    before_result = _mappings_result([_window_row(9, "before")])
    center_result = MagicMock()
    center_result.mappings.return_value.first.return_value = _window_row(10, "center")
    after_result = _mappings_result([_window_row(11, "after")])
    session.execute = AsyncMock(
        side_effect=[before_result, center_result, after_result]
    )

    window = await repo._window_for_anchor(10, before=1, after=1)

    assert [item.id for item in window] == [9, 10, 11]


@pytest.mark.asyncio
async def test_conversation_window_blocks_respects_max_total():
    session = AsyncMock()
    repo = MessageRepository(session)
    created = datetime.now(timezone.utc)

    async def fake_window(anchor_id: int, before: int, after: int):
        return [
            StoredMessage(
                id=anchor_id,
                role="user",
                content=f"m-{anchor_id}",
                created_at=created,
            )
            for _ in range(before + 1 + after)
        ]

    repo._window_for_anchor = AsyncMock(side_effect=fake_window)
    blocks = await repo.get_conversation_window_blocks(
        [1, 2, 3],
        before=2,
        after=2,
        max_total=4,
    )
    assert len(blocks) == 1
    assert len(blocks[0][1]) == 4


@pytest.mark.asyncio
async def test_conversation_window_blocks_empty_anchors():
    session = AsyncMock()
    repo = MessageRepository(session)
    assert await repo.get_conversation_window_blocks([]) == []


@pytest.mark.asyncio
async def test_message_get_by_ids_empty():
    session = AsyncMock()
    repo = MessageRepository(session)
    assert await repo.get_by_ids([]) == []
