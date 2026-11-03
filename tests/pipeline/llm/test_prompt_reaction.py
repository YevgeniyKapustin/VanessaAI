"""Prompt rendering: media kinds in <attachment> and stored reactions."""

from datetime import UTC, datetime

from vanessa.core.messages import ContextMessage, ImageAttachment
from vanessa.pipeline.llm.prompts.message_xml import message_attachment_blocks
from vanessa.pipeline.llm.prompts.prompt_format import format_message_line
from vanessa.pipeline.llm.prompts.session_format import format_session_messages

CREATED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _reaction(**overrides) -> ContextMessage:
    values = {
        "id": 5,
        "role": "reaction",
        "content": "🔥",
        "sender_telegram_id": None,
        "sender_name": "Evgeniy",
        "created_at": CREATED_AT,
        "reply_to_message_id": 17,
    }
    values.update(overrides)
    return ContextMessage(**values)


def test_stored_reaction_renders_as_a_reaction_element():
    line = format_message_line(_reaction())

    assert line.startswith("<reaction ")
    assert 'emoji="🔥"' in line
    assert 'to="17"' in line
    assert "<text>" not in line


def test_reaction_without_a_resolved_target_has_no_to_attribute():
    line = format_message_line(_reaction(reply_to_message_id=None))

    assert 'to="' not in line


def test_session_block_keeps_reactions_between_messages():
    rendered = format_session_messages([_reaction()])

    assert "<reaction " in rendered
    assert rendered.strip().startswith("<messages>")


def test_sticker_attachment_is_labelled_by_kind():
    attachment = ImageAttachment(
        data_url="data:image/jpeg;base64,AA==",
        kind="sticker",
        description="кот в очках",
    )

    blocks = message_attachment_blocks((attachment,))

    assert len(blocks) == 1
    assert 'type="sticker"' in blocks[0]
    assert "кот в очках" in blocks[0]


def test_photo_attachment_defaults_to_the_photo_type():
    attachment = ImageAttachment(data_url="data:image/jpeg;base64,AA==")

    blocks = message_attachment_blocks((attachment,))

    assert 'type="photo"' in blocks[0]
