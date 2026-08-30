from datetime import datetime


def format_message_time(value: datetime | None) -> str:
    if value is None:
        return "??.??.???? ??:??"
    local = value.astimezone() if value.tzinfo is not None else value
    return local.strftime("%d.%m.%Y %H:%M")
