import fakeredis.aioredis
import pytest

from services.agent_core import broker_worker as bw
from vanessa.broker.backends import Delivery
from vanessa.broker.redis_streams import RedisStreamBroker
from vanessa.broker.serialization import decode
from vanessa.contracts.messages import (
    TaskKind,
    TaskMessage,
    TurnReply,
    TurnRequest,
)
from vanessa.core.request_context import get_planning_started_signal, get_request_id
from vanessa.core.turn import ConversationTurnResult


class _FakeSessionCM:
    async def __aenter__(self) -> "_FakeSessionCM":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _FakeHandler:
    def __init__(self) -> None:
        self.result = ConversationTurnResult(
            action="reply", reason="intent", reply="hello", messages=["hello"]
        )
        self.turns: list = []
        self.request_ids: list[str] = []

    async def handle_incoming(self, turn):
        self.turns.append(turn)
        self.request_ids.append(get_request_id())
        # Simulate the decision gate passing (mirrors the real pipeline firing
        # the planning-started signal → the worker publishes TurnStarted).
        signal = get_planning_started_signal()
        if signal is not None:
            await signal()
        return self.result


@pytest.fixture
def broker():
    client = fakeredis.aioredis.FakeRedis()
    return RedisStreamBroker("redis://localhost:6379/0", client=client)


async def _publish_worker(broker, message) -> _FakeHandler:
    """Drive one delivery through the worker without a Postgres session."""
    fake_handler = _FakeHandler()

    class FakeFactory:
        def __call__(self):
            return _FakeSessionCM()

    original = bw.async_session_factory
    bw.async_session_factory = FakeFactory()
    try:
        worker = bw.BrokerTurnWorker(
            broker,
            stream="turns",
            group="agent-core",
            consumer="agent-core-test",
            handler_builder=lambda s: fake_handler,
        )
        await worker._handle(Delivery(stream="turns", stream_id="1-0", message=message))
    finally:
        bw.async_session_factory = original
    return fake_handler


async def _read_kinds(broker, stream: str) -> list[str]:
    response = await broker._client.xread({stream: "0"})
    kinds: list[str] = []
    for _, entries in response or []:
        for _, fields in entries:
            kinds.append(decode(fields).message_kind())
    return kinds


async def test_worker_publishes_started_and_reply(broker) -> None:
    request = TurnRequest(
        correlation_id="c1",
        telegram_chat_id=1,
        message="hello",
        sender_telegram_id=2,
        chat_type="group",
        reply_to="replies:bot-test:c1",
    )
    fake_handler = await _publish_worker(broker, request)

    # The pipeline received the turn mapped from the request.
    assert len(fake_handler.turns) == 1
    turn = fake_handler.turns[0]
    assert turn.telegram_chat_id == 1
    assert turn.message == "hello"
    assert turn.sender_telegram_id == 2
    # The transport request id was propagated into the pipeline context.
    assert fake_handler.request_ids == ["c1"]

    # Both TurnStarted and TurnReply landed on the private reply stream.
    assert await _read_kinds(broker, "replies:bot-test:c1") == [
        "turn_started",
        "turn_reply",
    ]

    # The reply carries the correlation id and the result fields.
    response = await broker._client.xread({"replies:bot-test:c1": "0"})
    _, entries = response[0]
    _, fields = entries[1]
    reply = decode(fields)
    assert isinstance(reply, TurnReply)
    assert reply.correlation_id == "c1"
    assert reply.reply == "hello"
    assert reply.action == "reply"


async def test_worker_ignores_non_turn_messages(broker) -> None:
    fake_handler = await _publish_worker(broker, TaskMessage(task=TaskKind.SWEEP))
    assert fake_handler.turns == []
    assert await _read_kinds(broker, "replies:bot-test:c1") == []


async def test_worker_without_reply_stream_still_runs_pipeline(broker) -> None:
    request = TurnRequest(
        correlation_id="c2", telegram_chat_id=1, message="x", sender_telegram_id=2
    )
    fake_handler = await _publish_worker(broker, request)
    assert len(fake_handler.turns) == 1
    # No reply_to → no reply published, but the pipeline still ran (no DLQ).
    assert await broker._client.xlen("turns:dlq") == 0
