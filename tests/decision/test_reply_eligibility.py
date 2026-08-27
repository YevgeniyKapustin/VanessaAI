import pytest

from app.core.messages import ContextMessage
from app.decision.detectors.intent import IntentDetector
from app.decision.detectors.noise import NoiseFilter, NoiseHeuristics
from app.decision.detectors.triggers import TriggerKeywordChecker
from app.decision.gate.reply_eligibility import ReplyEligibility
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.models import DecisionReason


@pytest.fixture
def eligibility() -> ReplyEligibility:
    return ReplyEligibility(
        IntentDetector(),
        TriggerKeywordChecker(("помоги",)),
        NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        ChatIgnoreRegistry(),
    )


def test_hard_ignore_dismissal(eligibility: ReplyEligibility):
    result = eligibility.hard_ignore("сгинь", [])

    assert result is not None
    assert result.tag == "dismissal"
    assert result.decision_reason == DecisionReason.DISMISSAL


def test_hard_ignore_quote_echo(eligibility: ReplyEligibility):
    line = "повтор цитаты бота один в один"
    recent = [ContextMessage(id=1, role="assistant", content=line)]

    result = eligibility.hard_ignore(line, recent, reply_to_bot=True)

    assert result is not None
    assert result.tag == "quote_echo"


def test_hard_ignore_ignored_user(eligibility: ReplyEligibility):
    eligibility._ignore_registry.ignore(1, 42)

    result = eligibility.hard_ignore(
        "привет",
        [],
        telegram_chat_id=1,
        sender_telegram_id=42,
    )

    assert result is not None
    assert result.tag == "ignored_user"


def test_prefilter_maps_side_talk_to_tag(eligibility: ReplyEligibility):
    verdict = eligibility.evaluate_prefilter(
        "Гриша меш гексы поле боя генерация",
        [],
    )

    assert verdict.run_planner is False
    assert verdict.reason == "side_talk"


def test_prefilter_defers_question_to_reaction_gate(eligibility: ReplyEligibility):
    verdict = eligibility.evaluate_prefilter("что думаешь про тик така", [])

    assert verdict.run_planner is True
    assert verdict.reason == "question"


def test_allows_compose_humor_ok(eligibility: ReplyEligibility):
    assert eligibility.allows_compose(
        "любой текст",
        humor_ok=True,
    ) is True


def test_allows_compose_blocks_reply_to_other(eligibility: ReplyEligibility):
    assert eligibility.allows_compose(
        "ответ другому",
        reply_to_other_user=True,
        should_reply=True,
    ) is False


def test_should_block_compose_allows_listen_window_follow_up(
    eligibility: ReplyEligibility,
):
    assert eligibility.should_block_compose(
        "втф чё с тобой",
        in_listen_window=True,
        should_reply=None,
    ) is False


def test_should_block_compose_blocks_outside_listen_window(
    eligibility: ReplyEligibility,
):
    assert eligibility.should_block_compose(
        "Гриша меш гексы поле боя генерация",
        in_listen_window=False,
        should_reply=None,
    ) is True


def test_should_block_compose_allows_question_outside_window(
    eligibility: ReplyEligibility,
):
    # A question in an active conversation is a compose candidate even outside
    # the listen window, so a session-approved question is not downgraded.
    assert eligibility.should_block_compose(
        "что думаешь про тик така",
        in_listen_window=False,
        should_reply=None,
    ) is False


def test_should_block_compose_blocks_reply_to_other(eligibility: ReplyEligibility):
    assert eligibility.should_block_compose(
        "ответ другому",
        reply_to_other_user=True,
        should_reply=True,
    ) is True


def test_should_block_compose_blocks_planner_veto_in_listen_window(
    eligibility: ReplyEligibility,
):
    assert eligibility.should_block_compose(
        "втф чё с тобой",
        in_listen_window=True,
        should_reply=False,
    ) is True


def test_should_block_compose_allows_direct_address_despite_planner_veto(
    eligibility: ReplyEligibility,
):
    # "ванесса + императив" is a direct address: the planner may misclassify
    # it as "общение между собой" (should_reply=False), but the deterministic
    # intent layer knows the bot was addressed — the veto must not silence it.
    assert eligibility.should_block_compose(
        "ванесса не тормози я написал",
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is False
    assert eligibility.should_block_compose(
        "ванесса отвечай",
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is False
    assert eligibility.should_block_compose(
        "ванесса, не молчи",
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is False


def test_should_block_compose_still_blocks_status_remark_despite_name(
    eligibility: ReplyEligibility,
):
    # The override is narrow: a status remark about the bot ("ванесса
    # работает") is NOT a direct address and stays silent even though the name
    # is present — the veto and the unsolicited-remark filter still hold.
    assert eligibility.should_block_compose(
        "ванесса работает",
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is True


def test_should_block_compose_honors_planner_veto_on_repeated_message(
    eligibility: ReplyEligibility,
):
    # The direct-address override must NOT rescue a repeated message: the
    # planner vetoed it (should_reply=False, «повтор»), and the same sender
    # already sent the same content — the repeat stays silent.
    recent = [
        ContextMessage(id=1, role="user", content="ванесса не тормози я написал", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="ванесса не тормози я написал", sender_telegram_id=7),
    ]
    assert eligibility.should_block_compose(
        "ванесса не тормози я написал",
        recent_messages=recent,
        sender_telegram_id=7,
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is True
    assert eligibility.should_block_compose(
        "ванесса отвечай",
        recent_messages=[
            ContextMessage(id=1, role="user", content="ванесса отвечай", sender_telegram_id=7),
            ContextMessage(id=2, role="user", content="ванесса отвечай", sender_telegram_id=7),
        ],
        sender_telegram_id=7,
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is True


def test_should_block_compose_does_not_block_non_repeat_direct_address_with_recent(
    eligibility: ReplyEligibility,
):
    # With a single occurrence in recent, the message is not a repeat — the
    # direct-address override still applies (regression guard for the previous
    # fix).
    recent = [
        ContextMessage(id=1, role="user", content="ванесса не тормози я написал", sender_telegram_id=7),
    ]
    assert eligibility.should_block_compose(
        "ванесса не тормози я написал",
        recent_messages=recent,
        sender_telegram_id=7,
        mentions_bot=False,
        reply_to_bot=False,
        should_reply=False,
        in_listen_window=False,
    ) is False


def _continuation_eligibility() -> ReplyEligibility:
    return ReplyEligibility(
        IntentDetector(),
        TriggerKeywordChecker(("помоги",)),
        NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        ChatIgnoreRegistry(),
        continuation_follow_up_enabled=True,
        continuation_phrases=("а ещё",),
    )


def _joke_follow_up_recent(interleaved: int = 2) -> list[ContextMessage]:
    """Bot replied to user 1's joke request; others interleaved; user 1: "а ещё"."""
    messages = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса расскажи анекдот",
            sender_telegram_id=1,
            sender_name="Юзер",
        ),
        ContextMessage(
            id=2,
            role="assistant",
            content="Ладно, слушай. Идёт мужик по кладбищу...",
        ),
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
    messages.append(
        ContextMessage(
            id=99,
            role="user",
            content="а ещё",
            sender_telegram_id=1,
            sender_name="Юзер",
        )
    )
    return messages


def test_prefilter_continuation_follow_up_passes_after_listen_window_expired():
    # Four other users wrote after the joke, so the 4-message listen window is
    # already expired — but the sender-aware continuation demand from the same
    # user the bot just answered still reaches the planner.
    eligibility = _continuation_eligibility()
    recent = _joke_follow_up_recent(interleaved=4)

    verdict = eligibility.evaluate_prefilter("а ещё", recent, sender_telegram_id=1)

    assert verdict.run_planner is True
    assert verdict.reason == "continuation"


def test_prefilter_continuation_requires_matching_sender():
    eligibility = _continuation_eligibility()
    recent = _joke_follow_up_recent(interleaved=4)

    # Someone else's "а ещё" is not an addressed continuation → side talk.
    verdict = eligibility.evaluate_prefilter("а ещё", recent, sender_telegram_id=5)

    assert verdict.run_planner is False
    assert verdict.reason == "side_talk"


def test_prefilter_continuation_disabled_falls_to_side_talk():
    eligibility = ReplyEligibility(
        IntentDetector(),
        TriggerKeywordChecker(("помоги",)),
        NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        ChatIgnoreRegistry(),
        continuation_follow_up_enabled=False,
        continuation_phrases=("а ещё",),
    )
    recent = _joke_follow_up_recent(interleaved=4)

    verdict = eligibility.evaluate_prefilter("а ещё", recent, sender_telegram_id=1)

    assert verdict.run_planner is False
    assert verdict.reason == "side_talk"
