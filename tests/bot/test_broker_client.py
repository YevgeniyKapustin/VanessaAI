import asyncio

import fakeredis.aioredis
import pytest
from aiogram import Bot

from services.bot.messages import IncomingMessage
from services.bot.services.broker_client import BrokerTurnClient
from vanessa.contracts.messages import InboxNoteReply, TurnReply, TurnStarted
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.owner_dm_store import PendingOwnerDm
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams

RELAY_CHAT = -1001


@pytest.fixture
def broker():
    client = fakeredis.aioredis.FakeRedis()
    return RedisStreamBroker("redis://localhost:6379/0", client=client)


def _incoming(
    chat_id: int = 1,
    message_id: int = 7,
    chat_title: str | None = None,
    *,
    chat_type: str = "group",
    sender_id: int = 2,
    sender_is_bot: bool = False,
    reply_to_message_id: int | None = None,
) -> IncomingMessage:
    return IncomingMessage(
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
        text="hello",
        sender_telegram_id=sender_id,
        chat_type=chat_type,
        chat_title=chat_title,
        sender_is_bot=sender_is_bot,
        reply_to_message_id=reply_to_message_id,
        bot=Bot(token="123456:TEST"),
    )


async def test_client_process_roundtrip(broker) -> None:
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(
        broker, streams=streams, timeout=3.0, bot_id="bot-1"
    )

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        assert req.channel == "telegram"
        await broker.publish(
            req.reply_to,
            TurnStarted(correlation_id=req.correlation_id),
        )
        await broker.publish(
            req.reply_to,
            TurnReply(
                correlation_id=req.correlation_id,
                action="reply",
                reason="intent",
                reply="pong",
                messages=["pong"],
                relevance_score=0.9,
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)

    started_calls: list[str] = []

    async def on_started() -> None:
        started_calls.append("started")

    result = await client.process(_incoming(), on_started=on_started)
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert started_calls == ["started"]
    assert result.action == "reply"
    assert result.reason == "intent"
    assert result.reply == "pong"
    assert result.messages == ["pong"]
    expected_score = 0.9
    assert result.relevance_score == expected_score


async def test_client_uses_correlation_id_from_message(broker) -> None:
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(broker, streams=streams, timeout=3.0, bot_id="bot-2")

    captured: list[str] = []

    async def agent_side(delivery: Delivery) -> None:
        req = delivery.message
        captured.append(req.correlation_id)
        await broker.publish(
            req.reply_to,
            TurnReply(correlation_id=req.correlation_id, action="ignore", reason="noise"),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    incoming = _incoming(chat_id=42, message_id=99)
    result = await client.process(incoming)
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert captured == ["42:99"]
    assert result.action == "ignore"


async def test_client_passes_known_group_and_returns_valid_send(
    broker, monkeypatch
) -> None:
    target_chat_id = -100
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(broker, streams=streams, timeout=3.0)
    captured = []
    monkeypatch.setattr("services.bot.services.broker_client.is_owner", lambda _: True)
    await broker.remember_chat(target_chat_id, "Known group", "supergroup")

    async def agent_side(delivery: Delivery) -> None:
        request = delivery.message
        captured.append(request)
        target = next(
            chat
            for chat in request.known_chats
            if chat.chat_id == target_chat_id
        )
        await broker.publish(
            request.reply_to,
            TurnReply(
                correlation_id=request.correlation_id,
                action="reply",
                reason="intent",
                reply="Sent",
                outbound_chat_id=target.chat_id,
                outbound_text="hello group",
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    result = await client.process(
        _incoming(chat_id=-101, chat_title="Source group")
    )
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert captured[0].sender_is_owner is True
    assert result.outbound_chat_id == target_chat_id
    assert result.outbound_text == "hello group"


@pytest.mark.asyncio
async def test_owner_dm_reply_carries_the_relayed_question(broker, monkeypatch) -> None:
    owner = 999
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(broker, streams=streams, timeout=3.0)
    monkeypatch.setattr("services.bot.services.broker_client.is_owner", lambda _: True)
    await broker.owner_dm_store().save(
        owner,
        55,
        PendingOwnerDm(
            chat_id=RELAY_CHAT,
            chat_title="Work chat",
            question="Когда релиз?",
            created_at="2026-10-30T10:00:00+00:00",
        ),
    )
    captured = []

    async def agent_side(delivery: Delivery) -> None:
        request = delivery.message
        captured.append(request)
        await broker.publish(
            request.reply_to,
            TurnReply(
                correlation_id=request.correlation_id,
                action="ignore",
                reason="owner_dm",
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    await client.process(
        _incoming(
            chat_id=owner,
            message_id=8,
            chat_type="private",
            sender_id=owner,
            reply_to_message_id=55,
        )
    )
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert captured[0].relay_chat_id == RELAY_CHAT
    assert captured[0].relay_chat_title == "Work chat"
    assert captured[0].relay_question == "Когда релиз?"


@pytest.mark.asyncio
async def test_owner_dm_text_passes_only_for_a_bot_sender(broker) -> None:
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")
    client = BrokerTurnClient(broker, streams=streams, timeout=3.0)

    async def agent_side(delivery: Delivery) -> None:
        request = delivery.message
        await broker.publish(
            request.reply_to,
            TurnReply(
                correlation_id=request.correlation_id,
                action="reply",
                reason="proxy_question",
                reply="Передала.",
                owner_dm_text="Какой срок?",
            ),
        )

    agent_task = asyncio.create_task(
        broker.consume_forever(
            streams.turns, "agent", "w1", agent_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    bot_result = await client.process(_incoming(chat_id=RELAY_CHAT, sender_is_bot=True))
    agent_task.cancel()
    await asyncio.gather(agent_task, return_exceptions=True)

    assert bot_result.owner_dm_text == "Какой срок?"


async def test_client_saves_inbox_note(broker) -> None:
    streams = BrokerStreams(
        prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks"
    )
    client = BrokerTurnClient(
        broker, streams=streams, timeout=3.0, bot_id="bot-note"
    )

    async def worker_side(delivery: Delivery) -> None:
        req = delivery.message
        await broker.publish(
            req.reply_to,
            InboxNoteReply(
                correlation_id=req.correlation_id,
                ok=True,
                path="inbox/note.md",
            ),
        )

    worker_task = asyncio.create_task(
        broker.consume_forever(
            streams.tasks, "worker", "w1", worker_side, poll_seconds=0.01
        )
    )
    await asyncio.sleep(0.05)
    path = await client.save_inbox_note(text="buy milk")
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
    assert path == "inbox/note.md"
