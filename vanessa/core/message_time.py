from datetime import datetime

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


def _local(value: datetime) -> datetime:
    return value.astimezone() if value.tzinfo is not None else value


def format_message_time(value: datetime | None) -> str:
    if value is None:
        return "??.??.???? ??:??"
    return _local(value).strftime("%d.%m.%Y %H:%M")


def format_current_time(value: datetime) -> str:
    """The time of the message being answered, with its weekday.

    Only the current message carries the weekday, so the model knows what
    day it is now («в пятницу» on a Saturday is wrong).
    """
    weekday = WEEKDAYS[_local(value).weekday()]
    return f"{format_message_time(value)}, {weekday}"
