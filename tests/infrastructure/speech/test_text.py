from vanessa.core.protocols.speech import SpeechAudio
from vanessa.infrastructure.speech import speakable_text
from vanessa.infrastructure.speech.text import _MAX_CHARS
from vanessa.infrastructure.speech.voice import voice_payload


def test_markdown_is_stripped() -> None:
    assert speakable_text("**привет**, _как_ `дела`?") == "привет, как дела?"


def test_links_keep_their_label_and_drop_the_url() -> None:
    text = "смотри [тут](https://example.com/a) и https://example.com/b"
    assert speakable_text(text) == "смотри тут и"


def test_code_fence_is_dropped() -> None:
    assert speakable_text("код:\n```python\nprint(1)\n```\nвсё") == "код:\nвсё"


def test_emoji_are_removed() -> None:
    assert speakable_text("привет 😀🔥") == "привет"


def test_blank_lines_collapse() -> None:
    assert speakable_text("раз\n\n\nдва") == "раз\nдва"


def test_long_reply_is_truncated_on_a_word_boundary() -> None:
    spoken = speakable_text("слово " * 1_000)
    assert len(spoken) <= _MAX_CHARS + 1
    assert spoken.endswith("…")
    assert "сло" not in spoken[-4:]


def test_empty_reply_stays_empty() -> None:
    assert speakable_text(None) == ""
    assert speakable_text("   ") == ""


def test_mp3_payload_keeps_the_bytes() -> None:
    payload, filename = voice_payload(
        SpeechAudio(pcm=b"ID3", sample_rate=44_100), output_format="mp3_44100_128"
    )
    assert (payload, filename) == (b"ID3", "voice.mp3")


def test_pcm_payload_is_wrapped_as_wav() -> None:
    payload, filename = voice_payload(
        SpeechAudio(pcm=b"\x00\x10", sample_rate=16_000), output_format="pcm_24000"
    )
    assert payload.startswith(b"RIFF")
    assert filename == "voice.wav"


def test_unknown_format_is_sent_as_ogg() -> None:
    payload, filename = voice_payload(
        SpeechAudio(pcm=b"OggS", sample_rate=48_000), output_format="opus_48000_64"
    )
    assert (payload, filename) == (b"OggS", "voice.ogg")
