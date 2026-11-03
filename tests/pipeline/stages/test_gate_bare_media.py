"""Stickers and GIFs are bare media: answered only when addressed/listening."""

import pytest

from vanessa.config.content import (
    get_gif_placeholder,
    get_photo_placeholder,
    get_sticker_placeholder,
)
from vanessa.core.messages import ImageAttachment
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.stages.gate_vision import is_bare_media

CHAT_ID = -100123
SENDER_ID = 42


def _ctx(text: str, *, images: tuple[ImageAttachment, ...] = ()) -> TurnPipelineContext:
    turn = ChatTurnInput(
        telegram_chat_id=CHAT_ID,
        message=text,
        sender_telegram_id=SENDER_ID,
        images=images,
    )
    return TurnPipelineContext(turn=turn)


def _image(kind: str = "sticker") -> ImageAttachment:
    return ImageAttachment(data_url="data:image/jpeg;base64,AA==", kind=kind)


def test_bare_sticker_is_bare_media():
    assert is_bare_media(_ctx(get_sticker_placeholder(), images=(_image(),))) is True


def test_sticker_with_its_emoji_is_still_bare_media():
    text = f"{get_sticker_placeholder()} 😀"
    assert is_bare_media(_ctx(text, images=(_image(),))) is True


def test_bare_gif_is_bare_media():
    assert is_bare_media(_ctx(get_gif_placeholder(), images=(_image("gif"),))) is True


def test_bare_photo_still_counts_as_bare_media():
    assert is_bare_media(_ctx(get_photo_placeholder(), images=(_image("photo"),))) is True


def test_captioned_media_is_regular_content():
    text = "лови мем с котом"
    assert is_bare_media(_ctx(text, images=(_image(),))) is False


def test_placeholder_without_an_image_is_plain_text():
    assert is_bare_media(_ctx(get_sticker_placeholder())) is False


@pytest.mark.parametrize("text", ["", "привет", get_photo_placeholder()])
def test_text_turns_are_not_media(text: str):
    assert is_bare_media(_ctx(text)) is False
