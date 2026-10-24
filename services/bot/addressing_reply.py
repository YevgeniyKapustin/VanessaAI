from dataclasses import dataclass

from vanessa.core.bot_senders import bot_sender_label


@dataclass(frozen=True, slots=True)
class ReplyAddressing:
    reply_to_bot: bool = False
    reply_to_other_user: bool = False
    reply_to_sender_telegram_id: int | None = None
    reply_to_message_id: int | None = None
    reply_to_text: str | None = None
    reply_to_sender_name: str | None = None


def _bot_username(bot: object | None) -> str:
    if bot is None:
        return ""
    cached = _username_from_cached_me(bot)
    if cached:
        return cached
    username = getattr(bot, "username", None)
    if username:
        return str(username).lower()
    return ""


def _username_from_cached_me(bot: object) -> str:
    me = getattr(bot, "_me", None)
    if me is None or not getattr(me, "username", None):
        return ""
    return str(me.username).lower()


def _reply_sender_name(from_user: object | None, *, own_bot: bool = False) -> str | None:
    if from_user is None:
        return None
    name = (
        getattr(from_user, "first_name", None)
        or getattr(from_user, "last_name", None)
        or getattr(from_user, "username", None)
    )
    if not own_bot and getattr(from_user, "is_bot", False) is True:
        return bot_sender_label(name)
    return name


def _reply_text(reply_to: object | None) -> str | None:
    """Best-effort text of the replied-to message (text, caption or sticker emoji)."""
    if reply_to is None:
        return None
    text = getattr(reply_to, "text", None) or getattr(reply_to, "caption", None)
    if text:
        return str(text).strip() or None
    return _sticker_reply_text(reply_to)


def _sticker_reply_text(reply_to: object) -> str | None:
    sticker = getattr(reply_to, "sticker", None)
    if sticker is None:
        return None
    emoji = getattr(sticker, "emoji", None)
    if not emoji:
        return None
    return f"[стикер {emoji}]"


def extract_reply_addressing(
    reply_to: object | None,
    *,
    bot_id: int | None,
) -> ReplyAddressing:
    if bot_id is None or reply_to is None or reply_to.from_user is None:
        return ReplyAddressing()
    reply_author_id = reply_to.from_user.id
    return ReplyAddressing(
        reply_to_bot=reply_author_id == bot_id,
        reply_to_other_user=reply_author_id != bot_id,
        reply_to_sender_telegram_id=reply_author_id,
        reply_to_message_id=getattr(reply_to, "message_id", None),
        reply_to_text=_reply_text(reply_to),
        reply_to_sender_name=_reply_sender_name(
            reply_to.from_user,
            own_bot=reply_author_id == bot_id,
        ),
    )
