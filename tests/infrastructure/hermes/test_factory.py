from types import SimpleNamespace

from vanessa.contracts import OutboundMessage
from vanessa.infrastructure.broker.streams import BrokerStreams
from vanessa.infrastructure.hermes import (
    HermesClient,
    create_hermes_client,
    hermes_session_id,
)


def _settings(*, enabled: bool = True, url: str = "http://hermes:8642"):
    return SimpleNamespace(
        hermes_enabled=enabled,
        hermes_url=url,
        hermes_api_key="secret",
        hermes_timeout_seconds=2.0,
    )


def test_factory_builds_client_when_enabled():
    assert isinstance(create_hermes_client(_settings()), HermesClient)


def test_factory_returns_none_when_disabled_or_no_url():
    assert create_hermes_client(_settings(enabled=False)) is None
    assert create_hermes_client(_settings(url="")) is None


def test_session_id_is_one_per_chat():
    assert hermes_session_id("telegram", -100123) == "vanessa-telegram--100123"


def test_outbound_stream_name():
    streams = BrokerStreams.from_settings(SimpleNamespace(broker_streams_prefix="v"))

    assert streams.outbound == "v:outbound"


def test_outbound_message_defaults():
    message = OutboundMessage(telegram_chat_id=1, text="hi")

    assert message.channel == "telegram"
    assert message.reply_to_message_id is None
    assert OutboundMessage.message_kind() == "outbound_message"
