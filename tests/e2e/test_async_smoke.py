"""End-to-end async smoke test: bot → broker → agent → broker → bot.

Wires the REAL ``BrokerTurnClient`` (bot transport) and the REAL
``BrokerTurnWorker`` (agent consumer) over a fakeredis broker, with a
fake pipeline handler standing in for the orchestrator. Exercises the full
RPC round-trip incl. the ``TurnStarted`` (typing) event and request-id
propagation.
"""

import asyncio
from typing import Self

import fakeredis.aioredis
from aiogram import Bot

from services.agent import broker_worker as bw
from services.bot.messages import IncomingMessage
from services.bot.services.broker_client import BrokerTurnClient
from vanessa.core.request_context import get_planning_started_signal, get_request_id
from vanessa.core.turn import ConversationTurnResult
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams


class _FakeSessionCM:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _FakePipeline:
    async def handle_incoming(self, turn):
        # Capture the propagated request id and fire the typing signal.
        request_id = get_request_id()
        signal = get_planning_started_signal()
        if signal is not None:
            await signal()
        return ConversationTurnResult(
            action="reply",
            reason="intent",
            reply=f"echo {turn.message} (req={request_id})",
            messages=[f"echo {turn.message}"],
        )


async def test_full_async_round_trip() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")

    # Agent-core side: consume turns, run the pipeline, reply.
    class FakeFactory:
        def __call__(self):
            return _FakeSessionCM()

    worker = bw.BrokerTurnWorker(
        broker,
        stream=streams.turns,
        group="agent",
        consumer="agent-smoke",
        handler_builder=lambda session: _FakePipeline(),
        session_factory=FakeFactory(),
        dedup=broker.dedup_guard(),
    )
    try:
        worker_task = asyncio.create_task(worker.run_forever())
        await asyncio.sleep(0.05)

        # Bot side: RPC client.
        bot_client = BrokerTurnClient(
            broker, streams=streams, timeout=3.0, bot_id="bot-smoke"
        )
        started: list[str] = []

        async def on_started() -> None:
            started.append("started")

        message = IncomingMessage(
            telegram_chat_id=1,
            telegram_message_id=42,
            text="привет",
            sender_telegram_id=2,
            chat_type="group",
            bot=Bot(token="123456:TEST"),
        )
        result = await bot_client.process(message, on_started=on_started)

        assert started == ["started"]
        assert result.action == "reply"
        assert result.reason == "intent"
        assert result.reply.startswith("echo привет")
    finally:
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
