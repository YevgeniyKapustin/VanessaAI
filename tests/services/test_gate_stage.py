import pytest

from app.core.messages import StoredMessage
from app.core.session.chat_session_state import ChatSessionState
from app.core.turn import ChatTurnInput
from app.decision import IntentDetector, NoiseFilter, TriggerKeywordChecker
from app.decision.gate.prefilter import PlannerPrefilter
from app.decision.models import DecisionAction, DecisionReason
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.stages import GateStage
from app.services.turn_metrics import TurnMetrics


class FakeMessageRepo:
    async def create(self, **kwargs: object):
        return None


class FakeIndexing:
    def __init__(self) -> None:
        self.scheduled: list[StoredMessage] = []

    def schedule(self, record: StoredMessage) -> None:
        self.scheduled.append(record)


class NoDecision:
    async def decide(self, *args: object, **kwargs: object):
        raise AssertionError("decision should not run")


@pytest.mark.asyncio
async def test_gate_stage_prefilter_skips_planner():
    prefilter = PlannerPrefilter(
        intent_detector=IntentDetector(bot_names=["vanessa"]),
        trigger_checker=TriggerKeywordChecker(keywords=[]),
        noise_filter=NoiseFilter(),
        post_reply_listen_count=3,
        post_reply_listen_idle_seconds=300.0,
    )
    metrics = TurnMetrics()
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=True,
        defer_index_on_ignore=True,
    )
    indexing = FakeIndexing()
    gate = GateStage(
        QueryRewriter(use_llm=False),
        NoDecision(),
        prefilter,
        config,
        metrics,
        FakeMessageRepo(),  # type: ignore[arg-type]
        indexing,  # type: ignore[arg-type]
    )
    user_msg = StoredMessage(id=1, role="user", content="ок")
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="ок",
            sender_telegram_id=1,
        ),
        user_msg=user_msg,
        session=ChatSessionState(
            messages=[],
            in_listen_window=False,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )

    should_continue = await gate.run(ctx)

    assert should_continue is False
    assert ctx.planner_skipped is True
    assert ctx.result is not None
    assert ctx.result.action == DecisionAction.IGNORE.value
    assert ctx.result.reason == DecisionReason.PREFILTER.value
    assert indexing.scheduled == [user_msg]
