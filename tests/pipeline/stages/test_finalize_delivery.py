from vanessa.config.channels import load_channel_profile
from vanessa.contracts.outbound import MESSAGE_MAX_CHARS
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.stages.finalize_delivery import (
    delivery_messages,
    one_message,
    photo_fields,
    reaction_from_reply,
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


def test_one_message_joins_agent_reply_blocks() -> None:
    assert one_message(["a", "b"]) == ["a\nb"]
    assert one_message(["a"]) == ["a"]


def test_agent_delivery_is_one_message() -> None:
    turn = ChatTurnInput(
        telegram_chat_id=1,
        message="hi",
        sender_telegram_id=2,
        sender_is_bot=True,
    )
    ctx = TurnPipelineContext(turn=turn)

    assert delivery_messages(ctx, "one\n[next]\ntwo") == ["one\ntwo"]


def test_one_message_cuts_to_the_wire_limit() -> None:
    result = one_message(["x" * MESSAGE_MAX_CHARS, "y"])
    assert len(result[0]) == MESSAGE_MAX_CHARS
    assert result[0].endswith("…")


def test_telegram_finalize_keeps_the_reaction_marker() -> None:
    ctx = _ctx("telegram")
    assert load_channel_profile("telegram").reactions is True
    clean, emoji = reaction_from_reply(ctx, "ага\n[reaction:🔥]")
    assert clean == "ага"
    assert emoji == "🔥"


def test_vrchat_finalize_strips_reactions_without_emitting_one() -> None:
    ctx = _ctx("vrchat")
    assert ctx.profile.reactions is False
    clean, emoji = reaction_from_reply(ctx, "ага\n[reaction:🔥]")
    assert "reaction" not in clean.lower()
    assert emoji is None
