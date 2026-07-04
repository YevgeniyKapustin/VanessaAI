import pytest

from app.core.messages import ContextMessage, StoredMessage
from app.core.session.chat_session_state import ChatSessionState
from app.core.turn import ChatTurnInput
from app.decision import IntentDetector, NoiseFilter, TriggerKeywordChecker
from app.decision.engine import DecisionEngine
from app.decision.gate.reply_eligibility import ReplyEligibility
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.detectors.rate_limit import RateLimiter
from app.decision.detectors.session_window import SessionWindowAnalyzer
from app.decision.models import DecisionAction, DecisionReason
from app.decision.detectors.noise import NoiseHeuristics
from app.llm.planner.turn_planner import TurnPlan
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.stages import GateStage
from app.services.turn_metrics import TurnMetrics


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


class FakeMessageRepo:
    async def create(self, **kwargs: object):
        return None


class FakeIndexing:
    def schedule(self, record: StoredMessage) -> None:
        pass


def _build_engine(relevance_score: float) -> DecisionEngine:
    intent = IntentDetector()
    triggers = TriggerKeywordChecker(())
    registry = ChatIgnoreRegistry()
    eligibility = ReplyEligibility(
        intent,
        triggers,
        NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        registry,
    )
    return DecisionEngine(
        intent_detector=intent,
        trigger_checker=triggers,
        relevance_checker=FakeRelevance(relevance_score),
        session_analyzer=SessionWindowAnalyzer(10, intent, triggers),
        rate_limiter=RateLimiter(max_replies=0),
        noise_filter=NoiseFilter(NoiseHeuristics(max_words=1, max_chars=12)),
        relevance_threshold=0.75,
        reply_eligibility=eligibility,
    )


def _gate_with_engine(engine: DecisionEngine) -> GateStage:
    registry = ChatIgnoreRegistry()
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=False,
        defer_index_on_ignore=True,
    )
    return GateStage(
        QueryRewriter(use_llm=False),
        engine,
        None,
        config,
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        registry,
    )


class ScriptedPlanner:
    def __init__(self, plan: TurnPlan) -> None:
        self._plan = plan

    async def prepare(self, *args: object, **kwargs: object) -> TurnPlan:
        return self._plan


@pytest.mark.asyncio
async def test_gate_stage_blocks_reply_to_other_via_decision_engine():
    engine = _build_engine(0.99)
    gate = GateStage(
        ScriptedPlanner(
            TurnPlan(
                original="x",
                text="",
                skip_search=True,
                should_reply=True,
                humor_ok=False,
            )
        ),  # type: ignore[arg-type]
        engine,
        None,
        OrchestratorConfig(
            session_window_size=10,
            session_idle_seconds=300.0,
            post_reply_listen_count=3,
            planner_prefilter_enabled=False,
            defer_index_on_ignore=True,
        ),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        ChatIgnoreRegistry(),
    )
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="Личь не делает карты по героям",
            sender_telegram_id=1,
            reply_to_other_user=True,
        ),
        user_msg=StoredMessage(id=1, role="user", content="x"),
        session=ChatSessionState(
            messages=[],
            in_listen_window=True,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )

    should_continue = await gate.run(ctx)

    assert should_continue is False
    assert ctx.result is not None
    assert ctx.result.action == DecisionAction.IGNORE.value
    assert ctx.result.reason == DecisionReason.NOT_EXPECTED.value


@pytest.mark.asyncio
async def test_gate_stage_allows_listen_window_follow_up():
    recent = [
        ContextMessage(id=1, role="user", content="ванесса..."),
        ContextMessage(id=2, role="assistant", content="Здесь, слушаю"),
        ContextMessage(id=3, role="user", content="втф чё с тобой"),
    ]
    engine = _build_engine(0.87)
    gate = GateStage(
        ScriptedPlanner(
            TurnPlan(
                original="втф чё с тобой",
                text="втф чё с тобой",
                skip_search=False,
                should_reply=None,
                humor_ok=False,
            )
        ),  # type: ignore[arg-type]
        engine,
        None,
        OrchestratorConfig(
            session_window_size=10,
            session_idle_seconds=300.0,
            post_reply_listen_count=3,
            planner_prefilter_enabled=False,
            defer_index_on_ignore=True,
        ),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        ChatIgnoreRegistry(),
    )
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="втф чё с тобой",
            sender_telegram_id=1,
        ),
        user_msg=StoredMessage(id=1, role="user", content="втф чё с тобой"),
        session=ChatSessionState(
            messages=recent,
            in_listen_window=True,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )
    ctx.recent = recent

    should_continue = await gate.run(ctx)

    assert should_continue is True
    assert ctx.decision is not None
    assert ctx.decision.action == DecisionAction.REPLY


@pytest.mark.asyncio
async def test_gate_stage_allows_contextual_nickname_address():
    recent = [
        ContextMessage(id=1, role="user", content="продолжай список гомункул"),
    ]
    gate = _gate_with_engine(_build_engine(0.1))
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="продолжай список гомункул",
            sender_telegram_id=1,
        ),
        user_msg=StoredMessage(id=1, role="user", content="продолжай список гомункул"),
        session=ChatSessionState(
            messages=recent,
            in_listen_window=True,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )
    ctx.recent = recent

    should_continue = await gate.run(ctx)

    assert should_continue is True
