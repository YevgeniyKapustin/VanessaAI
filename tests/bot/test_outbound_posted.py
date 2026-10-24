"""The bot tells the agent which follow-up texts really went out."""

from datetime import UTC, datetime

from services.bot.outbound import handle_outbound
from services.bot.outbound.consumer import _reporter
from services.bot.outbound.posted import PostedReporter, posted_record, posted_texts
from vanessa.contracts import OutboundMessage, PostedMessages
from vanessa.contracts.outbound import OutboundDocument
from vanessa.infrastructure.broker.backends import Delivery
from vanessa.infrastructure.broker.serialization import decode, encode
from vanessa.infrastructure.broker.streams import BrokerStreams

CHAT_ID = -100
TURNS = "vanessa:turns"
POSTED_AT = datetime(2026, 1, 3, 10, 0, tzinfo=UTC)
REPLY_TO = 77


class FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.texts: list[str] = []
        self._fail = fail

    async def send_message(self, _chat_id, text, **_kwargs) -> None:
        if self._fail:
            raise RuntimeError("telegram down")
        self.texts.append(text)


class FakeBroker:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.published: list[tuple[str, object]] = []
        self._error = error

    async def publish(self, stream: str, message) -> str:
        if self._error is not None:
            raise self._error
        self.published.append((stream, message))
        return "1-0"


def _outbound(**overrides) -> OutboundMessage:
    fields = {
        "telegram_chat_id": CHAT_ID,
        "text": "first part",
        "more_texts": ["second part", "third part"],
        "reply_to_message_id": REPLY_TO,
        "source": "hermes",
        "question": "what is the build status?",
    }
    return OutboundMessage(**{**fields, **overrides})


def _delivery(message) -> Delivery:
    return Delivery(stream="vanessa:outbound", stream_id="1-0", message=message)


def test_texts_keep_only_the_posted_extras() -> None:
    texts = posted_texts(_outbound(), delivered=True, more=1)
    assert texts == ["first part", "second part"]


def test_no_texts_when_nothing_was_delivered() -> None:
    assert posted_texts(_outbound(), delivered=False, more=0) == []


def test_text_of_a_failed_file_still_counts() -> None:
    document = OutboundDocument(file_name="r.html", content="<p>x</p>")
    message = _outbound(document=document, more_texts=[])
    assert posted_texts(message, delivered=False, more=0) == ["first part"]


def test_record_copies_the_follow_up() -> None:
    message = _outbound()
    record = posted_record(message, ["first part"], POSTED_AT)
    assert record is not None
    assert record.message_id == f"posted:{message.message_id}"
    assert record.correlation_id == message.correlation_id
    assert record.telegram_chat_id == CHAT_ID
    assert record.texts == ["first part"]
    assert record.posted_at == POSTED_AT
    assert record.reply_to_message_id == REPLY_TO
    assert record.question == "what is the build status?"
    assert record.source == "hermes"


def test_no_record_without_texts() -> None:
    assert posted_record(_outbound(), [], POSTED_AT) is None


def test_record_survives_the_wire() -> None:
    record = posted_record(_outbound(), ["a", "b"], POSTED_AT)
    decoded = decode(encode(record))
    assert isinstance(decoded, PostedMessages)
    assert decoded == record


async def test_reporter_publishes_to_turns() -> None:
    broker = FakeBroker()
    await PostedReporter(broker, TURNS).report(
        _outbound(), delivered=True, more=2, posted_at=POSTED_AT
    )
    [(stream, record)] = broker.published
    assert stream == TURNS
    assert record.texts == ["first part", "second part", "third part"]


async def test_reporter_skips_when_nothing_went_out() -> None:
    broker = FakeBroker()
    await PostedReporter(broker, TURNS).report(
        _outbound(), delivered=False, more=0, posted_at=POSTED_AT
    )
    assert broker.published == []


async def test_reporter_never_raises(caplog) -> None:
    broker = FakeBroker(error=RuntimeError("redis down"))
    await PostedReporter(broker, TURNS).report(
        _outbound(), delivered=True, more=0, posted_at=POSTED_AT
    )
    assert "outbound_history_failed" in caplog.text


async def test_handle_outbound_reports_all_posted_parts() -> None:
    bot, broker = FakeBot(), FakeBroker()
    reporter = PostedReporter(broker, TURNS)
    await handle_outbound(bot, _delivery(_outbound()), reporter=reporter)
    [(_stream, record)] = broker.published
    assert len(bot.texts) == len(record.texts)
    assert record.texts == ["first part", "second part", "third part"]
    assert record.posted_at.tzinfo is not None


async def test_handle_outbound_reports_nothing_after_a_send_error() -> None:
    broker = FakeBroker()
    reporter = PostedReporter(broker, TURNS)
    await handle_outbound(FakeBot(fail=True), _delivery(_outbound()), reporter=reporter)
    assert broker.published == []


async def test_handle_outbound_skips_a_wrong_chat() -> None:
    broker = FakeBroker()
    reporter = PostedReporter(broker, TURNS)
    await handle_outbound(
        FakeBot(), _delivery(_outbound()), allowed_chat_id=1, reporter=reporter
    )
    assert broker.published == []


def test_reporter_needs_a_turns_stream() -> None:
    broker = FakeBroker()
    assert _reporter(broker, BrokerStreams(prefix="v", turns="", tasks="t")) is None
    assert isinstance(_reporter(broker, BrokerStreams(prefix="v", turns=TURNS, tasks="t")), PostedReporter)
