"""Worker stores a chat reaction as a ``reaction`` row in the chat's channel."""

from unittest.mock import MagicMock

import pytest

from services.worker.handlers import reactions as reactions_module
from services.worker.handlers.reactions import REACTION_ROLE, ReactionHandler
from vanessa.contracts.messages import TaskKind, TaskMessage

CHAT_ID = -100123
MESSAGE_ID = 77
USER_ID = 42
#: Row id the repository lookup returns for the reacted-to message.
TARGET_ID = 17


class _Session:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


def _task(**payload) -> TaskMessage:
    return TaskMessage(task=TaskKind.REACTION, payload=payload)


@pytest.mark.asyncio
async def test_reaction_handler_links_the_reaction_to_its_message(monkeypatch):
    stored: dict = {}

    class _Repo:
        def __init__(self, _session) -> None:
            pass

        async def get_id_by_telegram_message_id(self, message_id, *, channel):
            stored["lookup"] = (message_id, channel)
            return TARGET_ID

        async def create(self, **kwargs):
            stored["row"] = kwargs

    monkeypatch.setattr(reactions_module.repository, "MessageRepository", _Repo)
    session = _Session()
    handler = ReactionHandler(lambda: session)

    await handler.handle(
        _task(
            telegram_chat_id=CHAT_ID,
            chat_type="supergroup",
            message_id=MESSAGE_ID,
            user_id=USER_ID,
            user_name="Evgeniy Kapustin",
            emoji="🔥",
        )
    )

    row = stored["row"]
    assert row["role"] == REACTION_ROLE
    assert row["content"] == "🔥"
    assert row["channel"] == f"telegram:{CHAT_ID}"
    assert row["reply_to_message_id"] == TARGET_ID
    assert row["sender_telegram_id"] == USER_ID
    assert stored["lookup"] == (MESSAGE_ID, f"telegram:{CHAT_ID}")
    assert session.committed is True


@pytest.mark.asyncio
async def test_reaction_handler_skips_an_incomplete_payload(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(
        reactions_module.repository, "MessageRepository", MagicMock()
    )
    handler = ReactionHandler(factory)

    await handler.handle(
        _task(telegram_chat_id=CHAT_ID, message_id=MESSAGE_ID, emoji="")
    )

    factory.assert_not_called()
