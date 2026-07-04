def resolve_sender_display_name(
    telegram_id: int | None,
    sender_name: str | None,
) -> str:
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
