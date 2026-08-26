import pytest

from app.config.settings import settings
from app.core.messages import ContextMessage
from app.decision.context import DecisionContext
from app.decision.detectors.intent import IntentDetector, IntentResult
from app.decision.detectors.noise import NoiseFilter, NoiseHeuristics
from app.decision.detectors.rate_limit import RateLimiter
from app.decision.detectors.session_window import SessionWindowAnalyzer
from app.decision.detectors.triggers import TriggerKeywordChecker, TriggerResult
from app.decision.metrics_rule import SenderMetricsRule, should_ignore_for_toxicity
from app.decision.models import DecisionAction, DecisionReason
from app.knowledge.metrics.schema import PersonMetrics

TOXIC_METRICS = PersonMetrics(toxicity=0.95, trust_score=10)
NEUTRAL_METRICS = PersonMetrics(toxicity=0.2, trust_score=80)


def _context(
    *,
    metrics: PersonMetrics | None = TOXIC_METRICS,
    mentions_bot: bool = False,
    reply_to_bot: bool = False,
    trigger_detected: bool = False,
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
        trigger=TriggerResult(detected=trigger_detected),
        session_active=False,
        relevance_score=0.0,
        should_reply=should_reply,
        mentions_bot=mentions_bot,
        reply_to_bot=reply_to_bot,
        in_listen_window=in_listen_window,
        sender_telegram_id=sender_id,
        sender_metrics=metrics,
    )


# --- pure policy function ---


def test_should_ignore_for_toxicity_true_on_persistent_profile():
    assert (
        should_ignore_for_toxicity(
            TOXIC_METRICS, sender_telegram_id=42, owner_telegram_id=0
        )
        is True
    )


def test_should_ignore_for_toxicity_false_when_missing_fields():
    metrics = PersonMetrics(toxicity=0.95)
    assert (
        should_ignore_for_toxicity(
            metrics, sender_telegram_id=42, owner_telegram_id=0
        )
        is False
    )


def test_should_ignore_for_toxicity_false_for_neutral():
    assert (
        should_ignore_for_toxicity(
            NEUTRAL_METRICS, sender_telegram_id=42, owner_telegram_id=0
        )
        is False
    )


def test_should_ignore_for_toxicity_never_for_owner():
    assert (
        should_ignore_for_toxicity(
            TOXIC_METRICS, sender_telegram_id=42, owner_telegram_id=42
        )
        is False
    )


# --- rule guards ---


def test_rule_returns_none_without_metrics():
    rule = SenderMetricsRule()
    assert rule.evaluate(_context(metrics=None)) is None


def test_rule_ignores_toxic_low_trust_sender():
    result = SenderMetricsRule().evaluate(_context())
    assert result is not None
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.TOXIC


def test_rule_returns_none_for_neutral_sender():
    assert SenderMetricsRule().evaluate(_context(metrics=NEUTRAL_METRICS)) is None


def test_rule_guard_direct_address():
    assert SenderMetricsRule().evaluate(_context(mentions_bot=True)) is None


def test_rule_guard_trigger():
    assert SenderMetricsRule().evaluate(_context(trigger_detected=True)) is None


def test_rule_guard_planner_reply():
    assert SenderMetricsRule().evaluate(_context(should_reply=True)) is None


def test_rule_guard_listen_window():
    assert SenderMetricsRule().evaluate(_context(in_listen_window=True)) is None


# --- engine integration ---


class FakeRelevance:
    async def score(self, text, query_vector=None, search_text=None) -> float:
        return 0.9


def build_engine(intent_detector, trigger_checker):
    from app.decision.engine import DecisionEngine

    return DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        relevance_checker=FakeRelevance(),
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
        block_consecutive_replies=False,
    )


@pytest.mark.asyncio
async def test_engine_ignores_toxic_low_trust_sender():
    engine = build_engine(IntentDetector(), TriggerKeywordChecker(()))
    result = await engine.decide(
        text="просто болтовня без смысла",
        telegram_chat_id=1,
        recent_messages=[],
        should_reply=None,
        sender_telegram_id=42,
        sender_metrics=TOXIC_METRICS,
    )
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.TOXIC


@pytest.mark.asyncio
async def test_engine_never_suppresses_neutral_sender():
    engine = build_engine(IntentDetector(), TriggerKeywordChecker(()))
    recent = [
        ContextMessage(id=1, role="user", content="ванесса помоги"),
        ContextMessage(id=2, role="assistant", content="давай"),
    ]
    result = await engine.decide(
        text="а почему?",
        telegram_chat_id=1,
        recent_messages=recent,
        should_reply=None,
        sender_telegram_id=42,
        sender_metrics=NEUTRAL_METRICS,
    )
    # a neutral profile must never trigger the toxic suppression
    assert result.reason != DecisionReason.TOXIC


@pytest.mark.asyncio
async def test_engine_owner_is_never_suppressed():
    owner_id = settings.required_user_telegram_id or 999
    engine = build_engine(IntentDetector(), TriggerKeywordChecker(()))
    result = await engine.decide(
        text="просто болтовня без смысла",
        telegram_chat_id=1,
        recent_messages=[],
        should_reply=None,
        sender_telegram_id=owner_id,
        sender_metrics=TOXIC_METRICS,
    )
    assert result.reason != DecisionReason.TOXIC
