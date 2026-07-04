import pytest

from app.core.messages import ContextMessage
from app.decision.intent import IntentDetector
from app.decision.models import DecisionAction, DecisionReason
from app.decision.noise import NoiseFilter, NoiseHeuristics
from app.decision.rate_limit import RateLimiter
from app.decision.session_window import SessionWindowAnalyzer
from app.decision.triggers import TriggerKeywordChecker


@pytest.fixture
def intent_detector() -> IntentDetector:
    return IntentDetector()


@pytest.fixture
def trigger_checker() -> TriggerKeywordChecker:
    return TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи"))


def test_intent_detects_question_mark(intent_detector: IntentDetector):
    result = intent_detector.detect("Как дела?")

    assert result.detected is True
    assert result.has_question is True


def test_intent_detects_bot_name(intent_detector: IntentDetector):
    result = intent_detector.detect("Vanessa, подскажи")

    assert result.detected is True
    assert result.mentions_bot is True


def test_intent_ignores_small_talk(intent_detector: IntentDetector):
    result = intent_detector.detect("ок понял")

    assert result.detected is False


def test_trigger_detects_keyword(trigger_checker: TriggerKeywordChecker):
    result = trigger_checker.detect("Помоги с задачей")

    assert result.detected is True
    assert result.keyword == "помоги"


def test_session_window_requires_request_in_history(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="просто болтовня"),
    ]

    assert analyzer.has_active_request(messages) is False


def test_session_window_detects_prior_question(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="Vanessa, как дела?"),
        ContextMessage(id=2, role="assistant", content="Хорошо"),
    ]

    assert analyzer.has_active_request(messages) is True


def test_session_window_closes_after_dismissal(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    analyzer = SessionWindowAnalyzer(10, intent_detector, trigger_checker)
    messages = [
        ContextMessage(id=1, role="user", content="Vanessa, как дела?"),
        ContextMessage(id=2, role="assistant", content="Хорошо"),
        ContextMessage(id=3, role="user", content="хватит"),
        ContextMessage(id=4, role="user", content="а про токены?"),
    ]

    assert analyzer.has_active_request(messages) is False


def test_rate_limiter_blocks_after_max_replies():
    limiter = RateLimiter(max_replies=2, window_seconds=60)

    limiter.record_reply(1)
    limiter.record_reply(1)

    assert limiter.is_limited(1) is True


class FakeRelevance:
    def __init__(self, score: float) -> None:
        self._score = score
        self.calls = 0

    async def score(
        self,
        text: str,
        query_vector: list[float] | None = None,
        search_text: str | None = None,
    ) -> float:
        self.calls += 1
        return self._score


def test_noise_filter_ignores_short_ack():
    noise = NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12))

    assert noise.is_noise("ок") is True
    assert noise.is_noise("👍") is True
    assert noise.is_noise("лол") is True
    assert noise.is_noise("Vanessa, как дела?") is False
    assert noise.is_noise("продолжай мысль") is False
    assert noise.is_noise("где там") is False
    assert noise.is_noise("скажи мне") is False
    assert noise.is_noise("ок понял") is False


def build_engine(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
    relevance_score: float,
    *,
    block_consecutive: bool = False,
) -> "DecisionEngine":
    from app.decision.engine import DecisionEngine

    return DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        relevance_checker=FakeRelevance(relevance_score),
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
        block_consecutive_replies=block_consecutive,
    )


@pytest.mark.asyncio
async def test_decision_engine_replies_in_listen_window_after_bot(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)
    recent = [
        ContextMessage(
            id=1,
            role="user",
            content="ванесса подскажи алгоритм генерации меша",
        ),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(
            id=3,
            role="user",
            content="Гриша меш гексы поле боя генерация",
        ),
    ]

    result = await engine.decide(
        text="Гриша меш гексы поле боя генерация",
        telegram_chat_id=1,
        recent_messages=recent,
        should_reply=False,
        in_listen_window=True,
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_replies_in_listen_window_after_other_user(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса подскажи меш"),
        ContextMessage(id=2, role="assistant", content="Кратко про меш"),
        ContextMessage(id=3, role="user", content="ок"),
        ContextMessage(
            id=4,
            role="user",
            content="Гриша меш гексы поле боя генерация",
        ),
    ]

    result = await engine.decide(
        text="Гриша меш гексы поле боя генерация",
        telegram_chat_id=1,
        recent_messages=recent,
        should_reply=False,
        in_listen_window=True,
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.LISTEN_WINDOW


@pytest.mark.asyncio
async def test_decision_engine_ignores_status_remark_in_listen_window(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 1.0)
    recent = [
        ContextMessage(id=1, role="user", content="ванесса как дела"),
        ContextMessage(id=2, role="assistant", content="Норм"),
        ContextMessage(id=3, role="user", content="видите"),
        ContextMessage(id=4, role="user", content="гомункул работает"),
    ]

    result = await engine.decide(
        text="гомункул работает",
        telegram_chat_id=1,
        recent_messages=recent,
        should_reply=False,
        in_listen_window=True,
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_dismissal_even_when_addressed(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 1.0)
    result = await engine.decide(
        text="ванесса хватит",
        telegram_chat_id=1,
        recent_messages=[],
        mentions_bot=True,
        should_reply=True,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.DISMISSAL


@pytest.mark.asyncio
async def test_decision_engine_ignores_side_talk_when_planner_says_no():
    from app.decision.engine import DecisionEngine
    from app.decision.intent import IntentDetector
    from app.decision.triggers import TriggerKeywordChecker

    engine = DecisionEngine(
        intent_detector=IntentDetector(),
        trigger_checker=TriggerKeywordChecker(("помоги", "объясни", "найди", "расскажи")),
        relevance_checker=FakeRelevance(0.99),
        session_analyzer=SessionWindowAnalyzer(10, IntentDetector(), TriggerKeywordChecker(("помоги",))),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
    )

    result = await engine.decide(
        text="что думаешь про тик така",
        telegram_chat_id=1,
        recent_messages=[],
        should_reply=False,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOT_EXPECTED


@pytest.mark.asyncio
async def test_decision_engine_replies_on_reply_to_bot(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)

    result = await engine.decide(
        text="да именно",
        telegram_chat_id=1,
        recent_messages=[],
        reply_to_bot=True,
        should_reply=False,
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.ADDRESSING


@pytest.mark.asyncio
async def test_decision_engine_reply_on_intent(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)

    result = await engine.decide(
        text="Vanessa, что нового?",
        telegram_chat_id=1,
        recent_messages=[],
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.INTENT


@pytest.mark.asyncio
async def test_decision_engine_reply_on_trigger(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)

    result = await engine.decide(
        text="Помоги с отчётом",
        telegram_chat_id=1,
        recent_messages=[],
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY


@pytest.mark.asyncio
async def test_decision_engine_skips_relevance_for_trigger(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    relevance = FakeRelevance(0.99)
    from app.decision.engine import DecisionEngine

    engine = DecisionEngine(
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        relevance_checker=relevance,
        session_analyzer=SessionWindowAnalyzer(10, intent_detector, trigger_checker),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
    )

    result = await engine.decide(
        text="расскажи про крабера",
        telegram_chat_id=1,
        recent_messages=[],
        search_text="крабер",
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY
    assert relevance.calls == 0


@pytest.mark.asyncio
async def test_decision_engine_reply_on_relevance_with_session(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.9)
    recent = [
        ContextMessage(id=1, role="user", content="Vanessa, расскажи про API"),
        ContextMessage(id=2, role="assistant", content="Кратко про API"),
        ContextMessage(id=3, role="user", content="про токены тоже интересно"),
    ]

    result = await engine.decide(
        text="про токены тоже интересно",
        telegram_chat_id=1,
        recent_messages=recent,
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.RELEVANT


@pytest.mark.asyncio
async def test_decision_engine_ignores_irrelevant_small_talk(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.2)

    result = await engine.decide(
        text="ага",
        telegram_chat_id=1,
        recent_messages=[],
    )

    assert result.action == DecisionAction.IGNORE


@pytest.mark.asyncio
async def test_decision_engine_ignores_noise(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.9)

    result = await engine.decide(
        text="ок",
        telegram_chat_id=1,
        recent_messages=[],
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NOISE


@pytest.mark.asyncio
async def test_decision_engine_skips_noise_when_trigger_present(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.1)

    result = await engine.decide(
        text="помоги",
        telegram_chat_id=1,
        recent_messages=[],
    )

    assert result.action == DecisionAction.REPLY
    assert result.reason == DecisionReason.FORCE_REPLY


@pytest.mark.asyncio
async def test_decision_engine_blocks_consecutive_replies(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 0.9, block_consecutive=True)
    recent = [
        ContextMessage(id=1, role="assistant", content="Уже ответила"),
    ]

    result = await engine.decide(
        text="продолжай мысль",
        telegram_chat_id=1,
        recent_messages=recent,
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.CONSECUTIVE


@pytest.mark.asyncio
async def test_decision_engine_ignores_closure_after_bot_chat(
    intent_detector: IntentDetector,
    trigger_checker: TriggerKeywordChecker,
):
    engine = build_engine(intent_detector, trigger_checker, 1.0)
    recent = [
        ContextMessage(id=1, role="user", content="расскажи про кейт"),
        ContextMessage(id=2, role="assistant", content="Михась просил добавить"),
        ContextMessage(
            id=3,
            role="user",
            content="ну ладно надо будет поработать пойти",
        ),
    ]

    result = await engine.decide(
        text="ну ладно надо будет поработать пойти",
        telegram_chat_id=1,
        recent_messages=recent,
        search_text="работа",
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reason == DecisionReason.NO_REPLY_NEEDED
