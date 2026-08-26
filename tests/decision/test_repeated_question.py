import pytest

from app.core.messages import ContextMessage
from app.decision.detectors.intent import IntentDetector
from app.decision.detectors.noise import NoiseFilter, NoiseHeuristics
from app.decision.detectors.rate_limit import RateLimiter
from app.decision.detectors.session_window import SessionWindowAnalyzer
from app.decision.detectors.triggers import TriggerKeywordChecker
from app.decision.models import DecisionAction, DecisionReason
from app.decision.repeated_question import (
    RepeatedQuestionRule,
    is_pure_repeat,
    message_tokens,
)


class FakeRelevance:
    def __init__(self, score: float) -> None:
        self._score = score

    async def score(
        self,
        text: str,
        query_vector: list[float] | None = None,
        search_text: str | None = None,
    ) -> float:
        return self._score


@pytest.fixture
def engine():
    from app.decision.engine import DecisionEngine

    intent = IntentDetector()
    trigger = TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи"))
    return DecisionEngine(
        intent_detector=intent,
        trigger_checker=trigger,
        relevance_checker=FakeRelevance(0.1),
        session_analyzer=SessionWindowAnalyzer(10, intent, trigger),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
    )


# --- unit: tokenization / repeat detection ---


def test_message_tokens_strips_stopwords_and_punct():
    tokens = message_tokens("Ванесса, как починить импорт в unity?!")
    assert tokens == {"ванесса", "починить", "импорт", "unity"}


def test_is_pure_repeat_identical():
    prior = message_tokens("как починить импорт в unity")
    assert is_pure_repeat(prior, prior) is True


def test_is_pure_repeat_shortened():
    current = message_tokens("как починить импорт unity")
    prior = message_tokens("как починить импорт в unity")
    assert is_pure_repeat(current, prior) is True


def test_is_pure_repeat_with_new_word_false():
    current = message_tokens("как починить импорт unity и выложить")
    prior = message_tokens("как починить импорт unity")
    assert is_pure_repeat(current, prior) is False


def test_is_pure_repeat_too_short_false():
    current = message_tokens("починить unity")
    prior = message_tokens("как починить импорт в unity на андроид")
    assert is_pure_repeat(current, prior) is False


def test_rule_ignores_unanswered_repeat():
    rule = RepeatedQuestionRule()
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как починить импорт в unity"),
        ContextMessage(id=2, role="user", content="и ещё вопрос"),
    ]
    from app.decision.context import DecisionContext
    from app.decision.detectors.intent import IntentDetector
    from app.decision.detectors.triggers import TriggerKeywordChecker

    intent = IntentDetector().detect("ванесса как починить импорт в unity")
    trigger = TriggerKeywordChecker(()).detect("ванесса как починить импорт в unity")
    context = DecisionContext(
        text="ванесса как починить импорт в unity",
        telegram_chat_id=1,
        recent_messages=recent,
        query_vector=None,
        intent=intent,
        trigger=trigger,
        session_active=True,
        relevance_score=0.0,
    )
    assert rule.evaluate(context) is None


# --- integration via the decision engine ---


@pytest.mark.asyncio
async def test_engine_ignores_repeated_question(engine):
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как починить импорт в unity"),
        ContextMessage(id=2, role="assistant", content="Зайди в окно импорта и нажми fix"),
    ]

    result = await engine.decide(
        text="ванесса как починить импорт в unity",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.REPEATED


@pytest.mark.asyncio
async def test_engine_ignores_shortened_repeat(engine):
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как починить импорт в unity"),
        ContextMessage(id=2, role="assistant", content="Зайди в окно импорта и нажми fix"),
    ]

    result = await engine.decide(
        text="ванесса как починить импорт unity",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.REPEATED


@pytest.mark.asyncio
async def test_engine_replies_expanded_follow_up(engine):
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как починить импорт в unity"),
        ContextMessage(id=2, role="assistant", content="Зайди в окно импорта и нажми fix"),
    ]

    result = await engine.decide(
        text="ванесса как починить импорт в unity и выложить в плей маркет",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
    )

    assert result.action == DecisionAction.REPLY


@pytest.mark.asyncio
async def test_engine_does_not_ignore_repeat_without_prior_answer(engine):
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как починить импорт в unity"),
        ContextMessage(id=2, role="user", content="и ещё вопрос про крабер"),
    ]

    result = await engine.decide(
        text="ванесса как починить импорт в unity",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
    )

    assert result.action == DecisionAction.REPLY
