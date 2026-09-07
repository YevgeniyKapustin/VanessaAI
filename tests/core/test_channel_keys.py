from vanessa.core.session.channel_keys import (
    as_session_key,
    dialogue_session_key,
    memory_dedup_key,
    turn_channel,
)


class _Turn:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def test_turn_channel_defaults_telegram():
    assert turn_channel(_Turn()) == "telegram"
    assert turn_channel(_Turn(channel="vrchat")) == "vrchat"


def test_dialogue_session_key_telegram_vs_vrchat():
    assert dialogue_session_key(channel="telegram", telegram_chat_id=-100) == (
        "telegram:-100"
    )
    assert dialogue_session_key(channel="vrchat", telegram_chat_id=0) == "vrchat"
    assert dialogue_session_key(channel="vrchat", telegram_chat_id=99) == "vrchat"
    assert dialogue_session_key(telegram_chat_id=0) == "vrchat"
    assert dialogue_session_key(telegram_chat_id=None) == "vrchat"


def test_as_session_key_never_uses_int_zero():
    assert as_session_key(0) == "vrchat"
    assert as_session_key(1) == "telegram:1"
    assert as_session_key("vrchat") == "vrchat"
    assert as_session_key("telegram:-100") == "telegram:-100"


def test_memory_dedup_key_uses_telegram_id_or_name_slug():
    assert memory_dedup_key(
        channel="telegram",
        sender_telegram_id=42,
        sender_name="Ann",
    ) == "memory:telegram:42"
    assert memory_dedup_key(
        channel="vrchat",
        sender_telegram_id=None,
        sender_name="Alice From VR",
    ) == "memory:vrchat:alice-from-vr"
