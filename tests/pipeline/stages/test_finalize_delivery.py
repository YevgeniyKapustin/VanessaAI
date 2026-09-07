from vanessa.config.channels import load_channel_profile
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.stages.finalize_delivery import (
    delivery_messages,
    photo_fields,
    sticker_from_reply,
)


def _ctx(channel: str) -> TurnPipelineContext:
    return TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=1 if channel == "telegram" else None,
            message="hi",
            sender_telegram_id=2 if channel == "telegram" else None,
            channel=channel,
        )
    )


def test_vrchat_finalize_strips_sticker_without_emitting_tag() -> None:
    ctx = _ctx("vrchat")
    assert ctx.profile.stickers is False
    clean, tag = sticker_from_reply(ctx, "ок\n[sticker:delight]")
    assert "sticker" not in clean.lower()
    assert tag is None


def test_telegram_finalize_keeps_sticker_tag() -> None:
    ctx = _ctx("telegram")
    assert load_channel_profile("telegram").stickers is True
    _clean, tag = sticker_from_reply(ctx, "ок\n[sticker:delight]")
    assert tag == "delight"


def test_vrchat_finalize_does_not_split_messages() -> None:
    ctx = _ctx("vrchat")
    messages = delivery_messages(ctx, "one [next] two")
    assert len(messages) == 1
    assert "[next]" not in messages[0]


def test_vrchat_finalize_drops_photo_fields() -> None:
    ctx = _ctx("vrchat")
    ctx.photo_file_id = "file-1"
    ctx.photo_data_url = "data:image/jpeg;base64,x"
    assert photo_fields(ctx) == (None, None)
