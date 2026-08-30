from vanessa.config.content import AppContent
from vanessa.knowledge.users.display_names import resolve_sender_display_name
from vanessa.core.messages import ContextMessage
from vanessa.pipeline.llm.prompts.context_format import format_message_time
from vanessa.pipeline.llm.prompts.message_xml import (
    BOT_SENDER,
    message_attachment_blocks,
    render_messages,
    render_msg,
)


def format_session_messages(
    messages: list[ContextMessage],
    content: AppContent | None = None,
) -> str:
    """Render the recent-session messages as an XML-like ``<messages>`` block.

    Each message becomes a ``<msg>`` element (``id``/``sender``/``time``
    attributes, a verbatim ``<text>`` child, plus ``<reply_text>`` and
    ``<attachment>`` children when present) — the dynamic input-block convention.
    Returns an empty string when there is nothing to render.
    """
    if not messages:
        return ""
    rendered: list[str] = []
    for message in messages:
        time_label = format_message_time(message.created_at)
        text = message.content.replace("\n", " ").strip()
        if not text:
            continue
        if message.role == "assistant":
            sender = BOT_SENDER
        else:
            sender = resolve_sender_display_name(
                message.sender_telegram_id,
                message.sender_name,
            )
        reply_text = message.reply_to_text
        if reply_text:
            reply_text = reply_text.replace("\n", " ").strip()
        rendered.append(
            render_msg(
                content=text,
                sender=sender,
                time=time_label,
                msg_id=message.id,
                reply_to=message.reply_to_message_id,
                reply_text=reply_text,
                attachments=message_attachment_blocks(
                    message.attachments,
                    message.photo_caption,
                ),
            )
        )
    return render_messages(rendered)


def session_context_messages(
    messages: list[ContextMessage],
    *,
    exclude_last: bool = True,
) -> list[ContextMessage]:
    if exclude_last and messages:
        return list(messages[:-1])
    return list(messages)
