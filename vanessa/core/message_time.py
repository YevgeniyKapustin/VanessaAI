"""Time labels Vanessa sees, in the chat zone (storage stays UTC)."""

from datetime import datetime

from vanessa.core.chat_zone import to_chat_time

#: ``datetime.weekday()`` order; fixed names, not the process locale.
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def format_message_time(value: datetime | None) -> str:
    if value is None:
        return "??.??.???? ??:??"
    return to_chat_time(value).strftime("%d.%m.%Y %H:%M")


def format_current_time(value: datetime) -> str:
    """The time of the message being answered, with its weekday.

    Only the current message carries the weekday, so the model knows what
    day it is now («в пятницу» on a Saturday is wrong).
    """
    weekday = WEEKDAYS[to_chat_time(value).weekday()]
    return f"{format_message_time(value)}, {weekday}"
