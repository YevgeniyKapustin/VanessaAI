from types import SimpleNamespace

import pytest
from aiogram.enums import ChatType

from services.bot.handlers import cross_chat_delivery
from services.bot.messages.response import ChatProcessResult

BOT_ID = 999
OWNER_ID = 7
TARGET_CHAT_ID = -1002


class _AccessGuard:
    async def owner_in_chat(self, _bot, _chat_id: int) -> bool:
        return True


class _Broker:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, stream: str, message) -> str:
        self.published.append((stream, message))
        return "1-0"


class _Bot:
    async def get_chat(self, _chat_id: int):
        return SimpleNamespace(type=ChatType.SUPERGROUP)

    async def me(self):
        return SimpleNamespace(id=999)

    async def get_chat_member(self, _chat_id: int, user_id: int):
        assert user_id == BOT_ID
        return SimpleNamespace(status="member", can_send_messages=True)


@pytest.mark.asyncio
async def test_sends_and_records_owner_action(monkeypatch) -> None:
    sent = []

    async def post_outbound(_bot, outbound):
        sent.append(outbound)
        return True

    monkeypatch.setattr(cross_chat_delivery, "post_outbound", post_outbound)
    monkeypatch.setattr(
        cross_chat_delivery,
        "is_owner",
        lambda user_id: user_id == OWNER_ID,
    )
    broker = _Broker()
    services = SimpleNamespace(
        access_guard=_AccessGuard(),
        broker=broker,
        streams=SimpleNamespace(turns="turns"),
    )
    message = SimpleNamespace(bot=_Bot())
    incoming = SimpleNamespace(
        sender_telegram_id=OWNER_ID,
        telegram_chat_id=-1001,
    )
    result = ChatProcessResult(
        action="reply",
        reason="intent",
        reply="I'll send it.",
        outbound_chat_id=TARGET_CHAT_ID,
        outbound_text="Hello group",
    )

    updated = await cross_chat_delivery.deliver_cross_chat_action(
        message, incoming, services, result
    )

    assert [(item.telegram_chat_id, item.text) for item in sent] == [
        (TARGET_CHAT_ID, "Hello group")
    ]
    assert updated.reply == "Отправила сообщение в другую группу."
    assert len(broker.published) == 1
    recorded = broker.published[0][1]
    assert recorded.telegram_chat_id == TARGET_CHAT_ID
    assert recorded.texts == ["Hello group"]


@pytest.mark.asyncio
async def test_non_owner_action_is_rejected(monkeypatch) -> None:
    async def unexpected_send(*_args):
        raise AssertionError("non-owner action must not send")

    monkeypatch.setattr(cross_chat_delivery, "post_outbound", unexpected_send)
    monkeypatch.setattr(cross_chat_delivery, "is_owner", lambda _user_id: False)
    services = SimpleNamespace(access_guard=_AccessGuard(), broker=None, streams=None)
    message = SimpleNamespace(bot=_Bot())
    incoming = SimpleNamespace(sender_telegram_id=8, telegram_chat_id=-1001)
    result = ChatProcessResult(
        action="reply",
        reason="intent",
        outbound_chat_id=TARGET_CHAT_ID,
        outbound_text="Hello group",
    )

    updated = await cross_chat_delivery.deliver_cross_chat_action(
        message, incoming, services, result
    )

    assert updated.reply == "Не смогла отправить сообщение в другую группу."
