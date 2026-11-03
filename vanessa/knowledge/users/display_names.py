from vanessa.core.bot_senders import is_bot_sender_label
from vanessa.knowledge.users.nicknames import canonical_name_for


def _canonical_sender_name(sender_name: str) -> str:
    if is_bot_sender_label(sender_name):
        return sender_name
    return canonical_name_for(sender_name) or sender_name


def resolve_sender_display_name(
    telegram_id: int | None,
    sender_name: str | None,
) -> str:
    # Canonicalize through the alias map first: a Telegram nickname like «ну я»
    # must render as the canonical name the chat actually uses («Гриша»). Unknown
    # names fall through to the raw value.
    if sender_name:
        return _canonical_sender_name(sender_name)
    if telegram_id is not None:
        return str(telegram_id)
    return "user"


def resolve_user_display_name(
    telegram_id: int,
    *,
    nickname: str | None = None,
    first_name: str | None = None,
    username: str | None = None,
) -> str:
    return resolve_sender_display_name(
        telegram_id,
        nickname or first_name or username,
    )
