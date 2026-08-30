from vanessa.core.users.nicknames import canonical_name_for


def resolve_sender_display_name(
    telegram_id: int | None,
    sender_name: str | None,
) -> str:
    # Canonicalize through the alias map first: a Telegram nickname like «ну я»
    # must render as the canonical name the chat actually uses («Гриша»). Unknown
    # names fall through to the raw value.
    canonical = canonical_name_for(sender_name)
    if canonical:
        return canonical
    if sender_name:
        return sender_name
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
