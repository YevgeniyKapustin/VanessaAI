from app.core.messages import ContextMessage
from app.decision.gate.continuation import (
    DEFAULT_CONTINUATION_PHRASES,
    is_continuation_phrase,
    is_sender_continuation_demand,
    last_bot_reply_partner_sender_id,
)


# --------------------------------------------------------------------------- #
# is_continuation_phrase
# --------------------------------------------------------------------------- #


def test_is_continuation_phrase_exact_match():
    assert is_continuation_phrase("а ещё", DEFAULT_CONTINUATION_PHRASES) is True
    assert is_continuation_phrase("ещё один", DEFAULT_CONTINUATION_PHRASES) is True
    assert is_continuation_phrase("давай ещё", DEFAULT_CONTINUATION_PHRASES) is True
    assert is_continuation_phrase("продолжай", DEFAULT_CONTINUATION_PHRASES) is True


def test_is_continuation_phrase_case_and_whitespace_insensitive():
    assert is_continuation_phrase("  А  ЕЩЁ ", DEFAULT_CONTINUATION_PHRASES) is True
    assert is_continuation_phrase("а Ещё", DEFAULT_CONTINUATION_PHRASES) is True


def test_is_continuation_phrase_allows_few_extra_words():
    # A short message that opens with a continuation phrase still reads as a
    # demand.
    assert is_continuation_phrase(
        "а ещё анекдот про программистов", DEFAULT_CONTINUATION_PHRASES
    ) is True


def test_is_continuation_phrase_rejects_long_message():
    # A full paragraph is a real message, not a continuation filler.
    long_text = "а ещё мне нужно объяснить как работает эта система целиком и полностью"
    assert is_continuation_phrase(long_text, DEFAULT_CONTINUATION_PHRASES) is False


def test_is_continuation_phrase_rejects_non_continuation():
    assert is_continuation_phrase("что думаешь про тик така", DEFAULT_CONTINUATION_PHRASES) is False
    assert is_continuation_phrase("", DEFAULT_CONTINUATION_PHRASES) is False


def test_is_continuation_phrase_uses_defaults_when_empty():
    assert is_continuation_phrase("а ещё", ()) is True
    assert is_continuation_phrase("а ещё", None) is True


def test_is_continuation_phrase_custom_list():
    assert is_continuation_phrase("ванесса ещё", ("ванесса ещё",)) is True
    assert is_continuation_phrase("а ещё", ("ванесса ещё",)) is False


# --------------------------------------------------------------------------- #
# last_bot_reply_partner_sender_id
# --------------------------------------------------------------------------- #


def _recent_with_reply(partner: int = 1, *, interleaved: int = 0) -> list[ContextMessage]:
    messages = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса расскажи анекдот",
            sender_telegram_id=partner,
            sender_name="Юзер",
        ),
        ContextMessage(id=2, role="assistant", content="Ладно, слушай..."),
    ]
    for index in range(interleaved):
        messages.append(
            ContextMessage(
                id=10 + index,
                role="user",
                content="хаха",
                sender_telegram_id=900 + index,
                sender_name=f"Друг{index}",
            )
        )
    return messages


def test_last_bot_reply_partner_sender_id():
    recent = _recent_with_reply(partner=7)
    assert last_bot_reply_partner_sender_id(recent) == 7


def test_last_bot_reply_partner_sender_id_with_interleaving():
    recent = _recent_with_reply(partner=7, interleaved=2)
    assert last_bot_reply_partner_sender_id(recent) == 7


def test_last_bot_reply_partner_sender_id_none_without_assistant():
    recent = [ContextMessage(id=1, role="user", content="привет", sender_telegram_id=1)]
    assert last_bot_reply_partner_sender_id(recent) is None


def test_last_bot_reply_partner_sender_id_none_when_no_prior_user():
    recent = [ContextMessage(id=1, role="assistant", content="привет")]
    assert last_bot_reply_partner_sender_id(recent) is None


# --------------------------------------------------------------------------- #
# is_sender_continuation_demand
# --------------------------------------------------------------------------- #


def test_sender_continuation_demand_match():
    recent = _recent_with_reply(partner=1) + [
        ContextMessage(id=5, role="user", content="а ещё", sender_telegram_id=1)
    ]
    assert is_sender_continuation_demand("а ещё", recent, 1) is True


def test_sender_continuation_demand_wrong_sender():
    recent = _recent_with_reply(partner=1) + [
        ContextMessage(id=5, role="user", content="а ещё", sender_telegram_id=2)
    ]
    assert is_sender_continuation_demand("а ещё", recent, 2) is False


def test_sender_continuation_demand_requires_sender():
    recent = _recent_with_reply(partner=1) + [
        ContextMessage(id=5, role="user", content="а ещё", sender_telegram_id=1)
    ]
    assert is_sender_continuation_demand("а ещё", recent, None) is False


def test_sender_continuation_demand_too_far_back():
    recent = _recent_with_reply(partner=1, interleaved=2) + [
        ContextMessage(id=5, role="user", content="а ещё", sender_telegram_id=1)
    ]
    # messages_since = 3 <= DEFAULT_MAX_MESSAGES_BACK, still matches.
    assert is_sender_continuation_demand("а ещё", recent, 1) is True
    # ...but a tight bound rejects it.
    assert (
        is_sender_continuation_demand("а ещё", recent, 1, max_messages_back=2)
        is False
    )


def test_sender_continuation_demand_without_assistant():
    recent = [ContextMessage(id=1, role="user", content="привет", sender_telegram_id=1)]
    assert is_sender_continuation_demand("а ещё", recent, 1) is False


def test_sender_continuation_demand_non_phrase():
    recent = _recent_with_reply(partner=1) + [
        ContextMessage(id=5, role="user", content="как дела", sender_telegram_id=1)
    ]
    assert is_sender_continuation_demand("как дела", recent, 1) is False
