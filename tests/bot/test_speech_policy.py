import pytest

from services.bot.speech_policy import (
    omits_text,
    should_send_voice,
    wants_voice_reply,
)

_REQUESTS = (
    "скажи голосом",
    "а теперь голосом, пожалуйста",
    "озвучь это",
    "можешь вслух?",
    "голосовое скинь",
    "send a voice note",
)


@pytest.mark.parametrize("text", _REQUESTS)
def test_voice_request_is_detected(text: str) -> None:
    assert wants_voice_reply(text) is True


@pytest.mark.parametrize(
    "text",
    ["привет", "как дела?", "у неё приятный голос", "", None],
)
def test_plain_text_does_not_trigger_voice(text: str | None) -> None:
    assert wants_voice_reply(text) is False


def test_on_request_mode_speaks_only_on_a_trigger() -> None:
    mode = "on_request"
    assert should_send_voice(mode=mode, requested=True, replied_to_voice=False) is True
    assert should_send_voice(mode=mode, requested=False, replied_to_voice=True) is True
    assert should_send_voice(mode=mode, requested=False, replied_to_voice=False) is False


@pytest.mark.parametrize("mode", ["voice_and_text", "voice_only"])
def test_always_modes_ignore_the_trigger(mode: str) -> None:
    assert should_send_voice(mode=mode, requested=False, replied_to_voice=False) is True


@pytest.mark.parametrize("mode", ["off", "", "unknown"])
def test_off_modes_never_speak(mode: str) -> None:
    assert should_send_voice(mode=mode, requested=True, replied_to_voice=True) is False


def test_text_is_kept_only_for_voice_and_text() -> None:
    assert omits_text(voice_sent=True, mode="on_request") is True
    assert omits_text(voice_sent=True, mode="voice_only") is True
    assert omits_text(voice_sent=True, mode="voice_and_text") is False
    assert omits_text(voice_sent=False, mode="on_request") is False
