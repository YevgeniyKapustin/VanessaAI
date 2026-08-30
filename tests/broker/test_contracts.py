from vanessa.contracts.messages import (
    SCHEMA_VERSION,
    BrokerMessage,
    TaskKind,
    TaskMessage,
    TurnImage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from vanessa.broker.errors import UnknownMessageKind
from vanessa.broker.serialization import decode, encode


def test_turn_request_round_trip() -> None:
    request = TurnRequest(
        correlation_id="req-1",
        telegram_chat_id=123,
        message="hello",
        sender_telegram_id=42,
        images=[TurnImage(data_url="data:image/jpeg;base64,abc")],
    )
    fields = encode(request)
    assert fields["kind"] == "turn_request"
    assert fields["correlation_id"] == "req-1"
    decoded = decode(fields)
    assert decoded == request
    assert isinstance(decoded, TurnRequest)
    assert decoded.images[0].data_url == "data:image/jpeg;base64,abc"


def test_turn_reply_round_trip() -> None:
    reply = TurnReply(
        correlation_id="req-1",
        action="reply",
        reason="intent",
        reply="Привет!",
        messages=["Привет!", "Как дела?"],
        context_count=3,
        relevance_score=0.9,
        sticker_tag="ok",
    )
    fields = encode(reply)
    decoded = decode(fields)
    assert decoded == reply
    assert isinstance(decoded, TurnReply)


def test_task_message_kind() -> None:
    task = TaskMessage(task=TaskKind.INDEX_MESSAGE, payload={"message_id": 7})
    assert task.message_kind() == "task"
    decoded = decode(encode(task))
    assert isinstance(decoded, TaskMessage)
    assert decoded.task == TaskKind.INDEX_MESSAGE
    assert decoded.payload == {"message_id": 7}


def test_every_kind_registers() -> None:
    for model in (TurnRequest, TurnStarted, TurnReply, TaskMessage):
        assert model.message_kind()  # non-empty stable kind


def test_unknown_kind_raises() -> None:
    try:
        decode({"kind": "bogus", "payload": "{}"})
    except UnknownMessageKind as exc:
        assert exc.kind == "bogus"
    else:  # pragma: no cover - must raise
        raise AssertionError("expected UnknownMessageKind")


def test_schema_version_stamped() -> None:
    message = TurnRequest(telegram_chat_id=1, message="x", sender_telegram_id=2)
    assert message.schema_version == SCHEMA_VERSION


def test_message_id_and_correlation_defaults_unique() -> None:
    a = TurnRequest(telegram_chat_id=1, message="x", sender_telegram_id=2)
    b = TurnRequest(telegram_chat_id=1, message="x", sender_telegram_id=2)
    assert a.message_id != b.message_id
    assert a.correlation_id != b.correlation_id
    assert isinstance(a, BrokerMessage)
