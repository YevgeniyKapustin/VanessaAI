"""Outbound messages with a generated HTML file go out as a document."""

from unittest.mock import MagicMock

import pytest
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from pydantic import ValidationError

from services.bot.outbound import handle_outbound, post_document
from services.bot.outbound.document import CAPTION_MAX_CHARS
from vanessa.contracts import OutboundDocument, OutboundMessage
from vanessa.infrastructure.broker.backends import Delivery

CHAT_ID = -100
REPLY_TO = 77
PAGE = "<!doctype html><html><body>Отчёт</body></html>"
TWO = 2


class FakeBot:
    """Records ``send_document`` / ``send_message``; ``fail`` picks errors."""

    def __init__(self, fail=None) -> None:
        self.documents: list[dict] = []
        self.messages: list[dict] = []
        self._fail = fail or (lambda _call: None)

    async def send_document(self, chat_id, document, **kwargs) -> None:
        call = {"chat_id": chat_id, "document": document, **kwargs}
        self.documents.append(call)
        error = self._fail(call)
        if error is not None:
            raise error

    async def send_message(self, chat_id, text, **kwargs) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})


def _message(text: str = "**Готово**", **overrides) -> OutboundMessage:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "text": text,
        "reply_to_message_id": REPLY_TO,
        "source": "hermes",
        "document": OutboundDocument(file_name="bugs.html", content=PAGE),
    }
    return OutboundMessage(**{**fields, **overrides})


def _bad_request() -> TelegramBadRequest:
    return TelegramBadRequest(MagicMock(), "can't parse entities")


async def test_document_goes_with_html_caption_as_reply() -> None:
    bot = FakeBot()
    delivery = Delivery(stream="vanessa:outbound", stream_id="1-0", message=_message())
    await handle_outbound(bot, delivery)
    assert bot.messages == []
    [call] = bot.documents
    assert call["chat_id"] == CHAT_ID
    assert call["caption"] == "<b>Готово</b>"
    assert call["parse_mode"] == ParseMode.HTML
    assert call["reply_parameters"].message_id == REPLY_TO
    assert call["document"].filename == "bugs.html"
    assert call["document"].data == PAGE.encode("utf-8")


async def test_long_text_goes_first_then_file_without_caption() -> None:
    bot = FakeBot()
    text = "a" * (CAPTION_MAX_CHARS + 1)
    assert await post_document(bot, _message(text, reply_to_message_id=None))
    assert len(bot.messages) == 1
    [call] = bot.documents
    assert call["caption"] is None
    assert call["reply_parameters"] is None


async def test_bad_caption_retries_plain() -> None:
    def fail(call):
        return _bad_request() if call["parse_mode"] == ParseMode.HTML else None

    bot = FakeBot(fail)
    assert await post_document(bot, _message())
    assert len(bot.documents) == TWO
    assert bot.documents[1]["caption"] == "**Готово**"
    assert bot.documents[1]["parse_mode"] is None
    assert bot.messages == []


async def test_failed_file_still_posts_the_text() -> None:
    bot = FakeBot(lambda _call: TelegramNetworkError(MagicMock(), "down"))
    assert not await post_document(bot, _message())
    assert len(bot.documents) == 1
    assert len(bot.messages) == 1


async def test_failed_file_after_long_text_posts_text_once() -> None:
    bot = FakeBot(lambda _call: _bad_request())
    text = "a" * (CAPTION_MAX_CHARS + 1)
    assert not await post_document(bot, _message(text))
    assert len(bot.documents) == 1
    assert len(bot.messages) == 1


async def test_without_document_posts_text() -> None:
    bot = FakeBot()
    assert await post_document(bot, _message(document=None))
    assert bot.documents == []
    assert len(bot.messages) == 1


@pytest.mark.parametrize(
    "name", ["../x.html", "x.htm", "x.js", "a b.html", "x" * 61 + ".html", ".html"]
)
def test_document_name_must_be_safe(name: str) -> None:
    with pytest.raises(ValidationError):
        OutboundDocument(file_name=name, content=PAGE)


def test_document_name_allows_unicode_letters() -> None:
    assert OutboundDocument(file_name="отчёт-1.html", content=PAGE).mime_type == "text/html"
