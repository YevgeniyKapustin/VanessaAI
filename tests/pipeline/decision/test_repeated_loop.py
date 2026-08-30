"""Tests for the repeated-topic-loop mechanic: detector, annoyance registry
and the LowAttitudeRule (maximal ignore tendency at critically low attitude).
"""

import pytest

from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.metrics.schema import PersonMetrics
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.detectors.triggers import TriggerResult
from vanessa.pipeline.decision.metrics_rule import LowAttitudeRule, is_low_attitude
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.decision.repeated_loop import (
    LoopRegistry,
    detect_loop_strength,
    topic_similarity,
)

# --- pure similarity ---


def test_topic_similarity_identical():
    assert topic_similarity({"меш", "текстуры"}, {"меш", "текстуры"}) == 1.0


def test_topic_similarity_disjoint():
    assert topic_similarity({"меш"}, {"крабер"}) == 0.0


def test_topic_similarity_empty():
    assert topic_similarity(set(), {"меш"}) == 0.0


# --- deterministic detector ---


def _recent(*texts: str, sender_id: int = 42) -> list[ContextMessage]:
    return [
        ContextMessage(
            id=i,
            role="user",
            content=text,
            sender_telegram_id=sender_id,
        )
        for i, text in enumerate(texts, start=1)
    ]


def test_detect_loop_strength_zero_on_new_topic():
    recent = _recent("расскажи про крабера и пещеру")
    assert (
        detect_loop_strength(
            "что там по работе у лича",
            recent,
            sender_telegram_id=42,
        )
        == 0
    )


def test_detect_loop_strength_one_repeat():
    recent = _recent("как сделать меш в unity")
    assert (
        detect_loop_strength(
            "а как же меш сделать",
            recent,
            sender_telegram_id=42,
        )
        == 1
    )


def test_detect_loop_strength_ignores_other_senders():
    other = ContextMessage(
        id=1,
        role="user",
        content="как сделать меш в unity",
        sender_telegram_id=7,
    )
    assert (
        detect_loop_strength(
            "а как же меш сделать",
            [other],
            sender_telegram_id=42,
        )
        == 0
    )


def test_detect_loop_strength_planner_signal():
    assert (
        detect_loop_strength(
            "ну что там с мешем",
            [],
            sender_telegram_id=42,
            planner_repeated=True,
            planner_loop_level=3,
        )
        == 3
    )
    assert (
        detect_loop_strength(
            "ну что там с мешем",
            [],
            sender_telegram_id=42,
            planner_repeated=True,
            planner_loop_level=9,
        )
        == 3
    )


# --- LoopRegistry ---


def test_registry_annoyance_rises_on_loop_and_resets_on_topic_change():
    registry = LoopRegistry()
    registry.update(
        42,
        "как сделать меш в unity",
        [],
        now=1_000.0,
    )
    signal = registry.update(
        42,
        "а как же меш сделать",
        _recent("как сделать меш в unity"),
        now=1_000.1,
    )
    assert signal.loop_strength >= 1
    assert signal.annoyance > 0.0
    # Topic changes → annoyance resets.
    signal = registry.update(
        42,
        "что там по работе у лича",
        _recent("как сделать меш в unity"),
        now=1_001.0,
    )
    assert signal.annoyance == 0.0


def test_registry_annoyance_decays_over_time():
    registry = LoopRegistry(decay_half_life_seconds=10.0)
    registry.update(42, "как сделать меш в unity", [], now=1_000.0)
    first = registry.update(
        42,
        "а как же меш сделать",
        _recent("как сделать меш в unity"),
        now=1_000.1,
    )
    assert first.annoyance > 0.0
    # A long pause on a DIFFERENT topic halves/decays the old annoyance.
    decayed = registry.update(
        42,
        "полностью новая тема про погоду",
        _recent("как сделать меш в unity"),
        now=1_000.0 + 10.0,
    )
    assert decayed.annoyance < first.annoyance


def test_registry_returns_zero_without_sender_id():
    registry = LoopRegistry()
    signal = registry.update(0, "любой текст", [])
    assert signal.loop_strength == 0
    assert signal.annoyance == 0.0


def test_registry_reset_clears_state():
    registry = LoopRegistry()
    registry.update(42, "меш unity", [])
    registry.reset()
    assert registry.update(42, "меш unity", [], now=2_000.0).annoyance == 0.0


# --- is_low_attitude ---


def test_is_low_attitude_by_annoyance():
    assert (
        is_low_attitude(
            annoyance=0.9,
            sender_metrics=None,
            annoyance_threshold=0.6,
            trust_threshold=25.0,
            sympathy_threshold=-0.3,
        )
        is True
    )


def test_is_low_attitude_by_persisted_metrics():
    metrics = PersonMetrics(trust_score=15, sympathy=-0.6)
    assert (
        is_low_attitude(
            annoyance=0.0,
            sender_metrics=metrics,
            annoyance_threshold=0.6,
            trust_threshold=25.0,
            sympathy_threshold=-0.3,
        )
        is True
    )


def test_is_low_attitude_false_for_neutral():
    metrics = PersonMetrics(trust_score=80, sympathy=0.3)
    assert (
        is_low_attitude(
            annoyance=0.0,
            sender_metrics=metrics,
            annoyance_threshold=0.6,
            trust_threshold=25.0,
            sympathy_threshold=-0.3,
        )
        is False
    )


def test_is_low_attitude_false_for_zero_baseline():
    # A brand-new zero-baseline card must never be treated as low attitude.
    metrics = PersonMetrics.zero()
    assert (
        is_low_attitude(
            annoyance=0.0,
            sender_metrics=metrics,
            annoyance_threshold=0.6,
            trust_threshold=25.0,
            sympathy_threshold=-0.3,
        )
        is False
    )


def test_is_low_attitude_false_when_fields_missing():
    metrics = PersonMetrics(trust_score=15)  # sympathy unknown
    assert (
        is_low_attitude(
            annoyance=0.0,
            sender_metrics=metrics,
            annoyance_threshold=0.6,
            trust_threshold=25.0,
            sympathy_threshold=-0.3,
        )
        is False
    )


# --- LowAttitudeRule ---


def _context(
    *,
    annoyance: float = 0.0,
    metrics: PersonMetrics | None = None,
    mentions_bot: bool = False,
    should_reply: bool | None = None,
    in_listen_window: bool = False,
    sender_id: int = 42,
) -> DecisionContext:
    return DecisionContext(
        text="просто болтовня без смысла",
        telegram_chat_id=1,
        recent_messages=[],
        query_vector=None,
        intent=IntentResult(detected=False, mentions_bot=mentions_bot),
        trigger=TriggerResult(detected=False),
        session_active=False,
        relevance_score=0.0,
        should_reply=should_reply,
        mentions_bot=mentions_bot,
        in_listen_window=in_listen_window,
        sender_telegram_id=sender_id,
        sender_metrics=metrics,
        annoyance=annoyance,
    )


def test_low_attitude_rule_ignores_weak_message_when_annoyed():
    result = LowAttitudeRule().evaluate(_context(annoyance=0.9, should_reply=False))
    assert result is not None
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.LOW_ATTITUDE


def test_low_attitude_rule_ignores_when_planner_neutral_and_annoyed():
    result = LowAttitudeRule().evaluate(_context(annoyance=0.9, should_reply=None))
    assert result is not None
    assert result.reason == DecisionReason.LOW_ATTITUDE


def test_low_attitude_rule_ignores_on_persisted_low_relationship():
    metrics = PersonMetrics(trust_score=10, sympathy=-0.7)
    result = LowAttitudeRule().evaluate(_context(metrics=metrics))
    assert result is not None
    assert result.reason == DecisionReason.LOW_ATTITUDE


def test_low_attitude_rule_returns_none_without_low_attitude():
    assert LowAttitudeRule().evaluate(_context(annoyance=0.1)) is None


def test_low_attitude_rule_does_not_ignore_direct_address():
    result = LowAttitudeRule().evaluate(
        _context(annoyance=0.9, mentions_bot=True, should_reply=True)
    )
    assert result is None


def test_low_attitude_rule_does_not_ignore_listen_window():
    result = LowAttitudeRule().evaluate(_context(annoyance=0.9, in_listen_window=True))
    assert result is None


def test_low_attitude_rule_does_not_ignore_planner_reply():
    result = LowAttitudeRule().evaluate(_context(annoyance=0.9, should_reply=True))
    assert result is None


def test_low_attitude_rule_never_for_owner():
    owner = settings.required_user_telegram_id or 999
    result = LowAttitudeRule().evaluate(
        _context(annoyance=0.9, should_reply=False, sender_id=owner)
    )
    assert result is None


@pytest.mark.asyncio
async def test_engine_low_attitude_ignores_weak_message():
    from vanessa.pipeline.decision.detectors.intent import IntentDetector
    from vanessa.pipeline.decision.detectors.noise import NoiseFilter, NoiseHeuristics
    from vanessa.pipeline.decision.detectors.rate_limit import RateLimiter
    from vanessa.pipeline.decision.detectors.session_window import SessionWindowAnalyzer
    from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker
    from vanessa.pipeline.decision.engine import DecisionEngine

    class FakeRelevance:
        async def score(self, text, query_vector=None, search_text=None) -> float:
            return 0.1

    engine = DecisionEngine(
        intent_detector=IntentDetector(),
        trigger_checker=TriggerKeywordChecker(()),
        relevance_checker=FakeRelevance(),
        session_analyzer=SessionWindowAnalyzer(
            10, IntentDetector(), TriggerKeywordChecker(())
        ),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
        block_consecutive_replies=False,
    )
    result = await engine.decide(
        text="просто болтовня без смысла",
        telegram_chat_id=1,
        recent_messages=[],
        should_reply=False,
        sender_telegram_id=42,
        annoyance=0.9,
    )
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.LOW_ATTITUDE


@pytest.mark.asyncio
async def test_engine_low_attitude_still_replies_to_direct_question():
    from vanessa.pipeline.decision.detectors.intent import IntentDetector
    from vanessa.pipeline.decision.detectors.noise import NoiseFilter, NoiseHeuristics
    from vanessa.pipeline.decision.detectors.rate_limit import RateLimiter
    from vanessa.pipeline.decision.detectors.session_window import SessionWindowAnalyzer
    from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker
    from vanessa.pipeline.decision.engine import DecisionEngine

    class FakeRelevance:
        async def score(self, text, query_vector=None, search_text=None) -> float:
            return 0.9

    engine = DecisionEngine(
        intent_detector=IntentDetector(),
        trigger_checker=TriggerKeywordChecker(()),
        relevance_checker=FakeRelevance(),
        session_analyzer=SessionWindowAnalyzer(
            10, IntentDetector(), TriggerKeywordChecker(())
        ),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
        block_consecutive_replies=False,
    )
    result = await engine.decide(
        text="ванесса, почему небо синее?",
        telegram_chat_id=1,
        recent_messages=[],
        mentions_bot=True,
        should_reply=True,
        sender_telegram_id=42,
        annoyance=0.9,
    )
    # A direct question is still answered (coldly via the compose note), never
    # suppressed by the low-attitude rule.
    assert result.action == DecisionAction.REPLY
    assert result.reason != DecisionReason.LOW_ATTITUDE
