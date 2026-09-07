from types import SimpleNamespace

from services.bot.addressing_mentions import (
    entity_mentions_bot,
    mention_fragment_is_bot,
    message_mentions_bot,
    text_mention_user_is_bot,
    text_mentions_username,
)


def test_text_mentions_username() -> None:
    assert text_mentions_username("@vanessa hi", "vanessa") is True
    assert text_mentions_username("hi", "") is False
    assert text_mentions_username("hi", "vanessa") is False


def test_text_mention_user_is_bot() -> None:
    entity = SimpleNamespace(user=SimpleNamespace(id=7))
    assert text_mention_user_is_bot(entity, bot_id=7) is True
    assert text_mention_user_is_bot(SimpleNamespace(user=None), bot_id=7) is False
    assert text_mention_user_is_bot(entity, bot_id=None) is False


def test_mention_fragment_and_entity() -> None:
    entity = SimpleNamespace(type="mention", offset=0, length=8, user=None)
    assert mention_fragment_is_bot(entity, "@vanessa", bot_username="vanessa") is True
    assert mention_fragment_is_bot(entity, "@vanessa", bot_username="") is False
    assert entity_mentions_bot(entity, "@vanessa", bot_id=1, bot_username="vanessa")
    other = SimpleNamespace(type="url", offset=0, length=1, user=None)
    assert entity_mentions_bot(other, "x", bot_id=1, bot_username="vanessa") is False
    mention = SimpleNamespace(
        type="text_mention",
        offset=0,
        length=1,
        user=SimpleNamespace(id=3),
    )
    assert entity_mentions_bot(mention, "x", bot_id=3, bot_username="v") is True


def test_message_mentions_bot_entities() -> None:
    message = SimpleNamespace(
        entities=[SimpleNamespace(type="mention", offset=0, length=8, user=None)]
    )
    assert message_mentions_bot(
        message, "@vanessa", bot_id=1, bot_username="vanessa"
    )
    empty = SimpleNamespace(entities=None)
    assert message_mentions_bot(empty, "hi", bot_id=1, bot_username="vanessa") is False
