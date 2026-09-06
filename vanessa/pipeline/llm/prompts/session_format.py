from vanessa.config.content import AppContent
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.users.display_names import resolve_sender_display_name
from vanessa.pipeline.llm.prompts.context_format import format_message_time
from vanessa.pipeline.llm.prompts.message_xml import (
    BOT_SENDER,
    message_attachment_blocks,
    render_messages,
    render_msg,
)


def _session_text(message: ContextMessage) -> str:
    return message.content.replace("\n", " ").strip()


def _session_sender(message: ContextMessage) -> str:
    if message.role == "assistant":
        return BOT_SENDER
    return resolve_sender_display_name(
        message.sender_telegram_id,
        message.sender_name,
    )


def _session_reply_text(message: ContextMessage) -> str | None:
    reply_text = message.reply_to_text
    if not reply_text:
        return reply_text
    return reply_text.replace("\n", " ").strip()


def _render_session_message(message: ContextMessage) -> str:
    return render_msg(
        content=_session_text(message),
        sender=_session_sender(message),
        time=format_message_time(message.created_at),
        msg_id=message.id,
        reply_to=message.reply_to_message_id,
        reply_text=_session_reply_text(message),
        attachments=message_attachment_blocks(
            message.attachments,
            message.photo_caption,
        ),
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
    del content
    if not messages:
        return ""
    rendered = [
        _render_session_message(message)
        for message in messages
        if _session_text(message)
    ]
    return render_messages(rendered)


def session_context_messages(
    messages: list[ContextMessage],
    *,
    exclude_last: bool = True,
) -> list[ContextMessage]:
    if exclude_last and messages:
        return list(messages[:-1])
    return list(messages)
