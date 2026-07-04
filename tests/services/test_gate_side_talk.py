import pytest

from app.core.messages import StoredMessage
from app.core.session.chat_session_state import ChatSessionState
from app.core.turn import ChatTurnInput
from app.decision import IntentDetector, NoiseFilter, TriggerKeywordChecker
from app.decision.gate.reply_eligibility import ReplyEligibility
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.models import DecisionAction, DecisionReason, DecisionResult
from app.llm.planner.turn_planner import TurnPlan
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.stages import GateStage
from app.services.turn_metrics import TurnMetrics


class FakeDecision:
    async def decide(self, *args: object, **kwargs: object) -> DecisionResult:
        return DecisionResult(
            action=DecisionAction.REPLY,
            reason=DecisionReason.FORCE_REPLY,
        )


class FakePlanner:
    async def prepare(self, *args: object, **kwargs: object) -> TurnPlan:
        return TurnPlan(
            original="Личь не делает карты",
            text="",
            skip_search=True,
            should_reply=True,
            humor_ok=False,
        )


class FakeMessageRepo:
    async def create(self, **kwargs: object):
        return None


class FakeIndexing:
    def schedule(self, record: StoredMessage) -> None:
        pass


def _gate_stage(
    planner: FakePlanner,
    decision: FakeDecision,
    config: OrchestratorConfig,
    metrics: TurnMetrics,
) -> GateStage:
    registry = ChatIgnoreRegistry()
    eligibility = ReplyEligibility(
        IntentDetector(),
        TriggerKeywordChecker(()),
        NoiseFilter(),
        registry,
    )
    return GateStage(
        planner,  # type: ignore[arg-type]
        decision,  # type: ignore[arg-type]
        None,
        eligibility,
        config,
        metrics,
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        registry,
    )


@pytest.mark.asyncio
async def test_gate_stage_blocks_reply_without_address_or_humor():
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=False,
        defer_index_on_ignore=True,
    )
    gate = _gate_stage(FakePlanner(), FakeDecision(), config, TurnMetrics())
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
async def test_gate_stage_allows_contextual_nickname_address():
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=False,
        defer_index_on_ignore=True,
    )
    gate = _gate_stage(FakePlanner(), FakeDecision(), config, TurnMetrics())
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="продолжай список гомункул",
            sender_telegram_id=1,
        ),
        user_msg=StoredMessage(id=1, role="user", content="продолжай список гомункул"),
        session=ChatSessionState(
            messages=[],
            in_listen_window=True,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )

    should_continue = await gate.run(ctx)

    assert should_continue is True
