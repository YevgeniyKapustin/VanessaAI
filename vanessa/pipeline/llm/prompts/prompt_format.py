from datetime import UTC, datetime

from vanessa.config.content import AppContent
from vanessa.core.messages import ContextBlock, ContextMessage, ImageAttachment
from vanessa.knowledge.users.display_names import resolve_sender_display_name
from vanessa.pipeline.llm.prompts.context_format import (
    block_time_range,
    format_message_time,
)
from vanessa.pipeline.llm.prompts.message_xml import (
    BOT_SENDER,
    message_attachment_blocks,
    render_messages,
    render_msg,
)


def format_message_line(message: ContextMessage) -> str:
    time_label = format_message_time(message.created_at)
    sender = BOT_SENDER
    if message.role != "assistant":
        sender = resolve_sender_display_name(
            message.sender_telegram_id,
            message.sender_name,
        )
    # One <msg> element (XML input-block convention): a verbatim <text>,
    # plus <reply_text> / <attachment> children and metadata attributes.
    return render_msg(
        content=message.content,
        sender=sender,
        time=time_label,
        msg_id=message.id,
        anchor=message.is_anchor,
        reply_to=message.reply_to_message_id,
        reply_text=message.reply_to_text,
        attachments=message_attachment_blocks(
            message.attachments,
            message.photo_caption,
        ),
    )


def format_context_block(
    content: AppContent, index: int, block: ContextBlock
) -> str:
    llm = content.llm
    started_at, ended_at = block_time_range(block.messages)
    header = llm.context_block_header.format(
        index=index,
        started_at=started_at,
        ended_at=ended_at,
    )
    lines = [format_message_line(message) for message in block.messages]
    return "\n".join([header, render_messages(lines)])


def format_current_message(
    content: str,
    *,
    sender_telegram_id: int | None = None,
    sender_name: str | None = None,
    created_at: datetime | None = None,
    reply_to_text: str | None = None,
    images: list[ImageAttachment] | None = None,
) -> str:
    """Render the current message as a ``<msg>`` element.

    ``images`` are the photos attached to THIS message (the current turn's
    own images). They are rendered as ``<attachment>`` children in the SAME
    ``<msg>`` as the ``<text>`` — the same convention as the session and
    context blocks — so the model always sees a photo right next to its
    caption instead of a detached album entry. Every attached photo is
    rendered (a message that carried several keeps them all together).
    """
    sender = resolve_sender_display_name(sender_telegram_id, sender_name)
    time_label = format_message_time(created_at or datetime.now(UTC))
    msg = render_msg(
        content=content,
        sender=sender,
        time=time_label,
        reply_text=reply_to_text,
        attachments=message_attachment_blocks(images) if images else None,
    )
    return render_messages([msg])
