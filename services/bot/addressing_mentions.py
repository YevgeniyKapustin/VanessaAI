def text_mentions_username(text: str, bot_username: str) -> bool:
    if not bot_username:
        return False
    return f"@{bot_username}" in text.lower()


def text_mention_user_is_bot(entity: object, *, bot_id: int | None) -> bool:
    user = entity.user
    if user is None or not bot_id:
        return False
    return user.id == bot_id


def mention_fragment_is_bot(
    entity: object,
    text: str,
    *,
    bot_username: str,
) -> bool:
    if not bot_username:
        return False
    fragment = text[entity.offset : entity.offset + entity.length]
    return fragment.lower().lstrip("@") == bot_username


def entity_mentions_bot(
    entity: object,
    text: str,
    *,
    bot_id: int | None,
    bot_username: str,
) -> bool:
    if entity.type == "text_mention":
        return text_mention_user_is_bot(entity, bot_id=bot_id)
    if entity.type == "mention":
        return mention_fragment_is_bot(entity, text, bot_username=bot_username)
    return False


def message_mentions_bot(
    message: object,
    text: str,
    *,
    bot_id: int | None,
    bot_username: str,
) -> bool:
    if text_mentions_username(text, bot_username):
        return True
    for entity in message.entities or []:
        if entity_mentions_bot(
            entity,
            text,
            bot_id=bot_id,
            bot_username=bot_username,
        ):
            return True
    return False
