"""Announcements go out as a rich card, with the plain text as the fallback."""

from unittest.mock import MagicMock

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from services.bot.outbound import handle_outbound, post_rich
from services.bot.outbound.rich import post_rich as post_rich_direct
from vanessa.contracts import OutboundDocument, OutboundMessage
from vanessa.infrastructure.broker.backends import Delivery

CHAT_ID = -100
REPLY_TO = 77
CARD = (
    '<p>Релиз <a href="https://git.example/-/pipelines/79545">v0.1.6 (79545)</a></p>'
    "<p>• Авто-MoA теперь и в веб-чате</p>"
    "<details><summary>разбор: 143 коммита, 2 карточки</summary></details>"
)
TEXT = "Релиз [v0.1.6 (79545)](https://git.example/-/pipelines/79545)\n\n• Авто-MoA"


class FakeBot:
    """Records ``send_rich_message`` / ``send_message``; ``fail`` picks errors."""

    def __init__(self, fail=None) -> None:
        self.rich: list[dict] = []
        self.messages: list[dict] = []
        self._fail = fail or (lambda _call: None)

    async def send_rich_message(self, chat_id, rich_message, **kwargs) -> None:
        call = {"chat_id": chat_id, "rich_message": rich_message, **kwargs}
        self.rich.append(call)
        error = self._fail(call)
        if error is not None:
            raise error

    async def send_message(self, chat_id, text, **kwargs) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})


def _message(**overrides) -> OutboundMessage:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "text": TEXT,
        "reply_to_message_id": REPLY_TO,
        "source": "deploy",
        "rich_html": CARD,
    }
    return OutboundMessage(**{**fields, **overrides})


def _bad_request() -> TelegramBadRequest:
    return TelegramBadRequest(MagicMock(), "can't parse entities")


async def test_card_goes_as_one_rich_message_reply() -> None:
    bot = FakeBot()
    assert await post_rich(bot, _message())
    [call] = bot.rich
    assert call["chat_id"] == CHAT_ID
    assert call["rich_message"].html == CARD
    assert call["reply_parameters"].message_id == REPLY_TO
    assert bot.messages == []


async def test_refused_card_falls_back_to_the_text() -> None:
    bot = FakeBot(lambda _call: _bad_request())
    assert await post_rich(bot, _message())
    assert len(bot.rich) == 1
    [message] = bot.messages
    assert message["text"].startswith("<b>Релиз</b>") or "Релиз" in message["text"]


async def test_network_error_also_falls_back_to_the_text() -> None:
    bot = FakeBot(lambda _call: TelegramNetworkError(MagicMock(), "down"))
    assert await post_rich(bot, _message())
    assert len(bot.messages) == 1


async def test_without_a_card_the_text_goes_out_alone() -> None:
    bot = FakeBot()
    assert await post_rich(bot, _message(rich_html=None))
    assert bot.rich == []
    assert len(bot.messages) == 1


async def test_the_consumer_prefers_the_card_over_plain_text() -> None:
    bot = FakeBot()
    delivery = Delivery(stream="vanessa:outbound", stream_id="1-0", message=_message())
    await handle_outbound(bot, delivery)
    assert len(bot.rich) == 1
    assert bot.messages == []


async def test_a_file_still_wins_over_the_card() -> None:
    bot = FakeBot()
    bot.documents = []

    async def send_document(chat_id, document, **kwargs) -> None:
        bot.documents.append({"chat_id": chat_id, "document": document, **kwargs})

    bot.send_document = send_document
    document = OutboundDocument(file_name="report.html", content="<html></html>")
    delivery = Delivery(
        stream="vanessa:outbound",
        stream_id="1-0",
        message=_message(document=document),
    )
    await handle_outbound(bot, delivery)
    assert bot.rich == []
    assert len(bot.documents) == 1


def test_the_module_exports_one_entry_point() -> None:
    assert post_rich is post_rich_direct
