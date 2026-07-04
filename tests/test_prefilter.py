import pytest

from app.core.messages import ContextMessage
from app.decision.intent import IntentDetector
from app.decision.noise import NoiseFilter, NoiseHeuristics
from app.decision.prefilter import PlannerPrefilter
from app.decision.triggers import TriggerKeywordChecker


@pytest.fixture
def prefilter() -> PlannerPrefilter:
    intent = IntentDetector()
    triggers = TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи"))
    return PlannerPrefilter(
        intent_detector=intent,
        trigger_checker=triggers,
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
    )


def test_prefilter_skips_side_talk(prefilter: PlannerPrefilter):
    result = prefilter.evaluate(
        "что думаешь про тик така",
        [],
    )

    assert result.run_planner is False
    assert result.reason == "side_talk"


def test_prefilter_runs_on_bot_name(prefilter: PlannerPrefilter):
    result = prefilter.evaluate(
        "Vanessa, что нового?",
        [],
    )

    assert result.run_planner is True
    assert result.reason == "bot_name"


def test_prefilter_runs_on_reply_to_bot(prefilter: PlannerPrefilter):
    result = prefilter.evaluate(
        "да именно",
        [],
        reply_to_bot=True,
    )

    assert result.run_planner is True
    assert result.reason == "direct_address"


def test_prefilter_skips_noise(prefilter: PlannerPrefilter):
    result = prefilter.evaluate("ок", [])

    assert result.run_planner is False
    assert result.reason == "noise"


def test_prefilter_runs_follow_up_question(prefilter: PlannerPrefilter):
    recent = [
        ContextMessage(id=1, role="user", content="Vanessa, расскажи"),
        ContextMessage(id=2, role="assistant", content="Кратко"),
        ContextMessage(id=3, role="user", content="а про токены?"),
    ]

    result = prefilter.evaluate("а про токены?", recent)

    assert result.run_planner is True
    assert result.reason == "listen_window"


def test_prefilter_listen_window_covers_side_talk_after_bot_reply(
    prefilter: PlannerPrefilter,
):
    recent = [
        ContextMessage(id=1, role="user", content="Vanessa, привет"),
        ContextMessage(id=2, role="assistant", content="Привет"),
        ContextMessage(id=3, role="user", content="что думаешь про тик така"),
    ]

    result = prefilter.evaluate("что думаешь про тик така", recent)

    assert result.run_planner is True
    assert result.reason == "listen_window"


def test_prefilter_listen_window_expires_after_five_user_messages(
    prefilter: PlannerPrefilter,
):
    recent = [
        ContextMessage(id=1, role="assistant", content="Ответ бота"),
        ContextMessage(id=2, role="user", content="один"),
        ContextMessage(id=3, role="user", content="два"),
        ContextMessage(id=4, role="user", content="три"),
        ContextMessage(id=5, role="user", content="четыре"),
        ContextMessage(id=6, role="user", content="пять"),
        ContextMessage(id=7, role="user", content="что думаешь про тик така"),
    ]

    result = prefilter.evaluate("что думаешь про тик така", recent)

    assert result.run_planner is False
    assert result.reason == "side_talk"


def test_prefilter_skips_dismissal(prefilter: PlannerPrefilter):
    result = prefilter.evaluate("ванесса хватит", [])

    assert result.run_planner is False
    assert result.reason == "dismissal"


def test_prefilter_closes_listen_window_after_dismissal(prefilter: PlannerPrefilter):
    recent = [
        ContextMessage(id=1, role="user", content="Vanessa, расскажи"),
        ContextMessage(id=2, role="assistant", content="Кратко"),
        ContextMessage(id=3, role="user", content="хватит"),
        ContextMessage(id=4, role="user", content="а про токены?"),
    ]

    result = prefilter.evaluate("а про токены?", recent)

    assert result.run_planner is False
    assert result.reason == "side_talk"


def test_prefilter_skips_status_remark_in_listen_window(
    prefilter: PlannerPrefilter,
):
    recent = [
        ContextMessage(id=1, role="user", content="Vanessa, привет"),
        ContextMessage(id=2, role="assistant", content="Привет"),
        ContextMessage(id=3, role="user", content="гомункул работает"),
    ]

    result = prefilter.evaluate("гомункул работает", recent)

    assert result.run_planner is False
    assert result.reason == "side_talk"
