from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_conversation_closure,
    is_third_party_about_bot,
    is_unsolicited_remark,
)


def is_unaddressed_reply_to_other(
    *,
    mentions_bot: bool,
    reply_to_bot: bool,
    reply_to_other_user: bool,
) -> bool:
    return reply_to_other_user and not mentions_bot and not reply_to_bot


def has_direct_mention_or_reply(
    *,
    mentions_bot: bool,
    reply_to_bot: bool,
    detected_mentions_bot: bool,
) -> bool:
    return mentions_bot or reply_to_bot or detected_mentions_bot


def open_question_warrants_reply(text: str, *, has_question: bool) -> bool:
    if not has_question:
        return False
    return not (
        is_conversation_closure(text)
        or is_unsolicited_remark(text)
        or is_third_party_about_bot(text)
    )
