"""A split follow-up: the first message (or file caption), then the rest."""

import pytest
from pydantic import ValidationError

from services.bot.outbound import handle_outbound
from services.bot.outbound.more import post_more_texts, should_post_more
from vanessa.contracts import OutboundDocument, OutboundMessage
from vanessa.contracts.outbound import MORE_TEXTS_MAX
from vanessa.infrastructure.broker.backends import Delivery

CHAT_ID = -100
REPLY_TO = 77
PAGE = "<!doctype html><html><body>Отчёт</body></html>"


class FakeBot:
    """Records sends; ``fail_texts`` makes ``send_message`` raise for them."""

    def __init__(self, fail_texts=(), *, fail_documents: bool = False) -> None:
        self.calls: list[tuple[str, str | None, dict]] = []
        self._fail_texts = set(fail_texts)
        self._fail_documents = fail_documents

    async def send_document(self, _chat_id, _document, **kwargs) -> None:
        self.calls.append(("document", kwargs.get("caption"), kwargs))
        if self._fail_documents:
            raise RuntimeError("telegram down")

    async def send_message(self, _chat_id, text, **kwargs) -> None:
        self.calls.append(("message", text, kwargs))
        if text in self._fail_texts:
            raise RuntimeError("telegram down")


def _message(**overrides) -> OutboundMessage:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "text": "Собрала отчёт",
        "reply_to_message_id": REPLY_TO,
        "source": "hermes",
        "more_texts": ["Три бага горят", "Один ждёт тебя"],
    }
    return OutboundMessage(**{**fields, **overrides})


def _delivery(message: OutboundMessage) -> Delivery:
    return Delivery(stream="vanessa:outbound", stream_id="1-0", message=message)


async def test_file_caption_then_more_messages_in_order(caplog) -> None:
    bot = FakeBot()
    document = OutboundDocument(file_name="bugs.html", content=PAGE)
    with caplog.at_level("INFO"):
        await handle_outbound(bot, _delivery(_message(document=document)))
    kinds = [(kind, text) for kind, text, _ in bot.calls]
    assert kinds == [
        ("document", "Собрала отчёт"),
        ("message", "Три бага горят"),
        ("message", "Один ждёт тебя"),
    ]
    assert bot.calls[0][2]["reply_parameters"].message_id == REPLY_TO
    assert all("reply_parameters" not in kwargs for _, _, kwargs in bot.calls[1:])
    assert "more=2/2" in caplog.text


async def test_text_only_then_more_messages() -> None:
    bot = FakeBot()
    await handle_outbound(bot, _delivery(_message()))
    texts = [text for _, text, _ in bot.calls]
    assert texts == ["Собрала отчёт", "Три бага горят", "Один ждёт тебя"]


async def test_more_messages_stop_on_first_failure() -> None:
    bot = FakeBot(fail_texts={"Три бага горят"})
    sent = await post_more_texts(bot, _message(), delay_seconds=0)
    assert sent == 0
    texts = [text for _, text, _ in bot.calls]
    assert "Один ждёт тебя" not in texts


async def test_failed_file_still_posts_text_and_more() -> None:
    bot = FakeBot(fail_documents=True)
    document = OutboundDocument(file_name="bugs.html", content=PAGE)
    await handle_outbound(bot, _delivery(_message(document=document)))
    texts = [text for kind, text, _ in bot.calls if kind == "message"]
    assert texts == ["Собрала отчёт", "Три бага горят", "Один ждёт тебя"]


def test_should_post_more_rules() -> None:
    assert should_post_more(_message(), delivered=True)
    assert not should_post_more(_message(), delivered=False)
    assert not should_post_more(_message(more_texts=[]), delivered=True)
    document = OutboundDocument(file_name="bugs.html", content=PAGE)
    assert should_post_more(_message(document=document), delivered=False)


async def test_failed_main_text_posts_nothing_more() -> None:
    bot = FakeBot(fail_texts={"Собрала отчёт"})
    await handle_outbound(bot, _delivery(_message()))
    texts = [text for _, text, _ in bot.calls]
    assert "Три бага горят" not in texts


def test_more_texts_are_capped_and_never_empty() -> None:
    with pytest.raises(ValidationError):
        _message(more_texts=["x"] * (MORE_TEXTS_MAX + 1))
    with pytest.raises(ValidationError):
        _message(more_texts=[""])
