from datetime import datetime

from app.core.messages import ContextBlock, ContextMessage


def format_message_time(value: datetime | None) -> str:
    if value is None:
        return "??.??.???? ??:??"
    local = value.astimezone() if value.tzinfo is not None else value
    return local.strftime("%d.%m.%Y %H:%M")


def block_time_range(messages: tuple[ContextMessage, ...]) -> tuple[str, str]:
    times = [message.created_at for message in messages if message.created_at]
    if not times:
        unknown = "??.??.???? ??:??"
        return unknown, unknown
    return format_message_time(min(times)), format_message_time(max(times))
