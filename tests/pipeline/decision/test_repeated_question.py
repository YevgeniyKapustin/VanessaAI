import pytest

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.detectors.intent import IntentDetector
from vanessa.pipeline.decision.detectors.noise import NoiseFilter, NoiseHeuristics
from vanessa.pipeline.decision.detectors.rate_limit import RateLimiter
from vanessa.pipeline.decision.detectors.session_window import SessionWindowAnalyzer
from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.decision.repeated_question import (
    RepeatedQuestionRule,
    is_pure_repeat,
    is_repeated_message,
    message_tokens,
    normalize_content,
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
    from vanessa.pipeline.decision.engine import DecisionEngine

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
    from vanessa.pipeline.decision.context import DecisionContext
    from vanessa.pipeline.decision.detectors.intent import IntentDetector
    from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker

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


def test_normalize_content_keeps_short_and_stopwords():
    # Short spam «ванесса» must match itself — unlike message_tokens (which
    # drops it for being <3 content words), normalize keeps stopwords.
    assert normalize_content("ванесса") == "ванесса"
    assert normalize_content("Ванесса!") == "ванесса"
    assert normalize_content("ну чё там") == "ну че там"
    assert normalize_content("ванесса,   ну чё?!") == "ванесса ну че"


def test_is_repeated_message_same_sender_burst():
    recent = [
        ContextMessage(id=1, role="user", content="ванесса", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="ванесса", sender_telegram_id=7),
    ]
    assert is_repeated_message("ванесса", recent, sender_telegram_id=7) is True


def test_is_repeated_message_single_occurrence_false():
    recent = [
        ContextMessage(id=1, role="user", content="ванесса", sender_telegram_id=7),
    ]
    assert is_repeated_message("ванесса", recent, sender_telegram_id=7) is False


def test_is_repeated_message_ignores_assistant_and_other_sender():
    recent = [
        ContextMessage(id=1, role="user", content="ванесса", sender_telegram_id=7),
        ContextMessage(id=2, role="assistant", content="ванесса"),
        ContextMessage(id=3, role="user", content="ванесса", sender_telegram_id=9),
    ]
    # Only same-sender user copies count; a different person's identical message
    # does not suppress this sender.
    assert is_repeated_message("ванесса", recent, sender_telegram_id=7) is False


def test_is_repeated_message_normalizes_punctuation_case():
    recent = [
        ContextMessage(id=1, role="user", content="ванесса, НУ чё?!", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="ванесса ну чё", sender_telegram_id=7),
    ]
    assert is_repeated_message("ванесса ну чё", recent, sender_telegram_id=7) is True


def test_rule_ignores_short_repeat_burst():
    rule = RepeatedQuestionRule()
    from vanessa.pipeline.decision.context import DecisionContext
    from vanessa.pipeline.decision.detectors.intent import IntentDetector
    from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker

    recent = [
        ContextMessage(id=1, role="user", content="ванесса", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="ванесса", sender_telegram_id=7),
    ]
    intent = IntentDetector().detect("ванесса")
    trigger = TriggerKeywordChecker(()).detect("ванесса")
    context = DecisionContext(
        text="ванесса",
        telegram_chat_id=1,
        recent_messages=recent,
        query_vector=None,
        intent=intent,
        trigger=trigger,
        session_active=True,
        relevance_score=0.0,
        sender_telegram_id=7,
    )
    result = rule.evaluate(context)
    assert result is not None
    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.REPEATED


def test_rule_defers_burst_when_planner_wants_reply():
    rule = RepeatedQuestionRule()
    from vanessa.pipeline.decision.context import DecisionContext
    from vanessa.pipeline.decision.detectors.intent import IntentDetector
    from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker

    recent = [
        ContextMessage(id=1, role="user", content="чек", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="чек", sender_telegram_id=7),
    ]
    intent = IntentDetector().detect("чек")
    trigger = TriggerKeywordChecker(()).detect("чек")
    context = DecisionContext(
        text="чек",
        telegram_chat_id=1,
        recent_messages=recent,
        query_vector=None,
        intent=intent,
        trigger=trigger,
        session_active=True,
        relevance_score=0.0,
        sender_telegram_id=7,
        should_reply=True,
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


@pytest.mark.asyncio
async def test_engine_ignores_same_sender_short_burst(engine):
    # Same sender spams the same short message («ванесса») — a burst is spam,
    # not a new question, even without any assistant reply in between.
    recent = [
        ContextMessage(id=1, role="user", content="ванесса", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="ванесса", sender_telegram_id=7),
    ]

    result = await engine.decide(
        text="ванесса",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
        sender_telegram_id=7,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.REPEATED


@pytest.mark.asyncio
async def test_engine_replies_short_burst_when_planner_says_yes(engine):
    recent = [
        ContextMessage(id=1, role="user", content="чек", sender_telegram_id=7),
        ContextMessage(id=2, role="user", content="чек", sender_telegram_id=7),
    ]

    result = await engine.decide(
        text="чек",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=False,
        should_reply=True,
        sender_telegram_id=7,
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.PLANNER


@pytest.mark.asyncio
async def test_engine_does_not_suppress_other_senders_similar_message(engine):
    # Person B's identical message does not suppress person A's — burst
    # detection is sender-aware.
    recent = [
        ContextMessage(id=1, role="user", content="ванесса ну чё", sender_telegram_id=7),
    ]

    result = await engine.decide(
        text="ванесса ну чё",
        telegram_chat_id=1,
        recent_messages=recent,
        mentions_bot=True,
        should_reply=None,
        sender_telegram_id=9,
    )

    assert result.action == DecisionAction.REPLY
