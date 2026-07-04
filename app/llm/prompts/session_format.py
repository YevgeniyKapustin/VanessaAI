from app.config.content import AppContent, get_content
from app.core.users.display_names import resolve_sender_display_name
from app.core.messages import ContextMessage
from app.llm.prompts.context_format import format_message_time


def format_session_messages(
    messages: list[ContextMessage],
    content: AppContent | None = None,
) -> str:
    if not messages:
        return ""
    llm = (content or get_content()).llm
    lines: list[str] = []
    for message in messages:
        time_label = format_message_time(message.created_at)
        text = message.content.replace("\n", " ").strip()
        if not text:
            continue
        if message.role == "assistant":
            lines.append(
                llm.session_assistant_line.format(
                    time=time_label,
                    content=text,
                )
            )
        else:
            sender = resolve_sender_display_name(
                message.sender_telegram_id,
                message.sender_name,
            )
            lines.append(
                llm.session_user_line.format(
                    time=time_label,
                    sender=sender,
                    content=text,
                )
            )
    return "\n".join(lines)


def session_context_messages(
    messages: list[ContextMessage],
    *,
    exclude_last: bool = True,
) -> list[ContextMessage]:
    if exclude_last and messages:
        return list(messages[:-1])
    return list(messages)
