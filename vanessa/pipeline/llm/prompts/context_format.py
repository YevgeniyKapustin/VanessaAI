from vanessa.core.message_time import format_message_time
from vanessa.core.messages import ContextMessage

__all__ = ["block_time_range", "format_message_time"]


def block_time_range(messages: tuple[ContextMessage, ...]) -> tuple[str, str]:
    times = [message.created_at for message in messages if message.created_at]
    if not times:
        unknown = "??.??.???? ??:??"
        return unknown, unknown
    return format_message_time(min(times)), format_message_time(max(times))
