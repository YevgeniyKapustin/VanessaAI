"""Owner DM delivery: send the proxy question, remember it, report the post."""

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.methods import SendMessage

from services.bot.handlers import owner_dm_delivery
from services.bot.messages.response import ChatProcessResult
from vanessa.config.settings import settings

OWNER = 999
SOURCE_CHAT = -1001


class _Store:
    def __init__(self) -> None:
        self.entries: list[tuple[int, int, object]] = []

    async def save(self, owner_id: int, message_id: int, pending) -> None:
        self.entries.append((owner_id, message_id, pending))


class _Broker:
    def __init__(self) -> None:
        self.store = _Store()
        self.published: list[tuple[str, object]] = []

    def owner_dm_store(self) -> _Store:
        return self.store

    async def publish(self, stream: str, message) -> str:
        self.published.append((stream, message))
        return "1-0"


class _Bot:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self._error = error

    async def send_message(self, chat_id: int, text: str, **kwargs):
        _ = kwargs
        if self._error is not None:
            raise self._error
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=55)


def _result() -> ChatProcessResult:
    return ChatProcessResult(
        action="reply",
        reason="proxy_question",
        reply="Передала.",
        owner_dm_text="Какой срок по релизу?",
    )


def _services(broker: _Broker) -> SimpleNamespace:
    return SimpleNamespace(broker=broker, streams=SimpleNamespace(turns="turns"))


def _incoming() -> SimpleNamespace:
    return SimpleNamespace(
        telegram_chat_id=SOURCE_CHAT,
        chat_title="Work chat",
        text="Евгений, когда релиз?",
        sender_telegram_id=777,
    )


@pytest.mark.asyncio
async def test_delivers_and_remembers_the_question(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    broker = _Broker()
    bot = _Bot()

    updated = await owner_dm_delivery.deliver_owner_dm_action(
        SimpleNamespace(bot=bot), _incoming(), _services(broker), _result()
    )

    assert bot.sent == [(OWNER, "Какой срок по релизу?")]
    assert updated.owner_dm_text is None
    owner_id, message_id, pending = broker.store.entries[0]
    assert (owner_id, message_id) == (OWNER, 55)
    assert pending.chat_id == SOURCE_CHAT
    assert pending.question.startswith("Евгений")
    _, posted = broker.published[0]
    assert posted.telegram_chat_id == OWNER
    assert posted.texts == ["Какой срок по релизу?"]


@pytest.mark.asyncio
async def test_telegram_failure_keeps_the_chat_reply(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    broker = _Broker()
    error = TelegramAPIError(SendMessage(chat_id=OWNER, text="x"), "forbidden")

    updated = await owner_dm_delivery.deliver_owner_dm_action(
        SimpleNamespace(bot=_Bot(error)), _incoming(), _services(broker), _result()
    )

    assert updated.reply == "Передала."
    assert broker.store.entries == []
    assert broker.published == []


@pytest.mark.asyncio
async def test_no_owner_id_skips_the_dm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", 0)
    broker = _Broker()
    bot = _Bot()

    updated = await owner_dm_delivery.deliver_owner_dm_action(
        SimpleNamespace(bot=bot), _incoming(), _services(broker), _result()
    )

    assert bot.sent == []
    assert updated.owner_dm_text is None


class _FallbackBot(_Bot):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def send_message(self, chat_id: int, text: str, **kwargs):
        _ = kwargs
        self.calls += 1
        if self.calls == 1:
            raise TelegramBadRequest(SendMessage(chat_id=OWNER, text="x"), "bad html")
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=77)


@pytest.mark.asyncio
async def test_bad_html_falls_back_to_plain_text(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    bot = _FallbackBot()

    await owner_dm_delivery.deliver_owner_dm_action(
        SimpleNamespace(bot=bot), _incoming(), _services(_Broker()), _result()
    )

    assert bot.sent == [(OWNER, "Какой срок по релизу?")]


@pytest.mark.asyncio
async def test_dm_is_sent_even_without_a_turns_stream(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", OWNER)
    broker = _Broker()
    services = SimpleNamespace(broker=broker, streams=None)

    await owner_dm_delivery.deliver_owner_dm_action(
        SimpleNamespace(bot=_Bot()), _incoming(), services, _result()
    )

    assert broker.store.entries != []
    assert broker.published == []
