"""A bot sender keeps its messages in history but gets no person card."""

from unittest.mock import AsyncMock

import pytest

from vanessa.core.messages import ContextMessage, StoredMessage
from vanessa.core.turn import ChatTurnInput
from vanessa.knowledge.memory.memory_transcript import format_memory_transcript
from vanessa.knowledge.metrics.batch_filters import drop_bot_messages
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.orchestrator.post_reply import _PostReplyMixin
from vanessa.pipeline.orchestrator.turn_ingress import _resolve_ingress_sender

KIRILL = 777


def _bot_turn() -> ChatTurnInput:
    return ChatTurnInput(
        telegram_chat_id=-100,
        message="привет, Ванесса",
        sender_telegram_id=KIRILL,
        sender_first_name="Kirill",
        sender_username="kirill_ai_bot",
        sender_is_bot=True,
    )


class _NoUsers:
    async def get_or_create(self, **kwargs):
        raise AssertionError(f"bot sender must not get a user row: {kwargs}")


@pytest.mark.asyncio
async def test_ingress_labels_bot_without_user_row():
    assert await _resolve_ingress_sender(_NoUsers(), _bot_turn()) == "[бот Kirill]"


class _Disp:
    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, kind, payload, **kwargs) -> None:
        self.submitted.append((kind, payload, kwargs))


class _Harness(_PostReplyMixin):
    def __init__(self, dispatcher: _Disp, memory) -> None:
        self._dispatcher = dispatcher
        self._memory = memory
        self._metrics = memory
        self._background = None
        self._eval = None
        self._photo_captioner = None
        self._session_factory = None
        self._messages = None


@pytest.mark.asyncio
async def test_bot_sender_gets_no_memory_or_metrics_job():
    dispatcher = _Disp()
    memory = AsyncMock()
    ctx = TurnPipelineContext(turn=_bot_turn())
    ctx.user_msg = StoredMessage(id=5, role="user", content="привет")

    await _Harness(dispatcher, memory)._run_post_reply(ctx)

    assert dispatcher.submitted == []
    memory.run.assert_not_awaited()


def test_memory_transcript_skips_bot_lines():
    transcript = format_memory_transcript(
        [
            ContextMessage(
                id=1,
                role="user",
                content="я Кирилл, запомни меня",
                sender_telegram_id=KIRILL,
                sender_name="[бот Kirill]",
            ),
            ContextMessage(
                id=2,
                role="user",
                content="а я человек",
                sender_telegram_id=1,
                sender_name="Женя",
            ),
            ContextMessage(id=3, role="assistant", content="ок"),
        ]
    )
    assert "Кирилл" not in transcript
    assert "а я человек" in transcript
    assert "[assistant] ок" in transcript


def test_metrics_batch_drops_bot_messages():
    batch = [
        StoredMessage(id=1, role="user", content="a", sender_name="[бот Kirill]"),
        StoredMessage(id=2, role="user", content="b", sender_name="Женя"),
        StoredMessage(id=3, role="assistant", content="c"),
    ]
    assert [message.id for message in drop_bot_messages(batch)] == [2, 3]
