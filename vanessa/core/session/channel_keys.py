import re

CHANNEL_TELEGRAM = "telegram"
CHANNEL_VRCHAT = "vrchat"

_UNSAFE = re.compile(r"[^\w\-]+", re.UNICODE)
_DASHES = re.compile(r"-+")


def turn_channel(turn: object) -> str:
    channel = getattr(turn, "channel", None)
    if isinstance(channel, str) and channel:
        return channel
    return CHANNEL_TELEGRAM


def dialogue_session_key(
    *,
    channel: str | None = None,
    telegram_chat_id: int | None = None,
) -> str:
    if channel == CHANNEL_VRCHAT:
        return CHANNEL_VRCHAT
    if not channel and not telegram_chat_id:
        return CHANNEL_VRCHAT
    return f"{CHANNEL_TELEGRAM}:{telegram_chat_id}"


def as_session_key(chat_id: int | str | None, *, channel: str | None = None) -> str:
    if isinstance(chat_id, str):
        return chat_id
    return dialogue_session_key(channel=channel, telegram_chat_id=chat_id)


def name_slug(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value.strip().lower())
    cleaned = _DASHES.sub("-", cleaned).strip("-")
    return cleaned or "unknown"


def memory_dedup_key(
    *,
    channel: str,
    sender_telegram_id: int | None,
    sender_name: str = "",
) -> str:
    if sender_telegram_id is not None:
        identity = str(sender_telegram_id)
    else:
        identity = name_slug(sender_name)
    return f"memory:{channel}:{identity}"
