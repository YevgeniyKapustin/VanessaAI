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
    verdict = eligibility.evaluate_prefilter("что думаешь про тик така", [])

    assert verdict.run_planner is False
    assert verdict.reason == "side_talk"


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
