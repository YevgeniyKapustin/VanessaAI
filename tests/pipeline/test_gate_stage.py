import pytest

from vanessa.core.messages import StoredMessage
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision import IntentDetector, NoiseFilter, TriggerKeywordChecker
from vanessa.pipeline.decision.gate.eligibility.prefilter import PlannerPrefilter
from vanessa.pipeline.decision.gate.eligibility.reply_eligibility import (
    ReplyEligibility,
)
from vanessa.pipeline.decision.gate.eligibility.user_ignore import ChatIgnoreRegistry
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages import GateStage
from vanessa.pipeline.turn_metrics import TurnMetrics


class FakeMessageRepo:
    async def create(self, **kwargs: object):
        _ = kwargs


class NoDecision:
    async def decide(self, *args: object, **kwargs: object):
        _ = args, kwargs
        raise AssertionError("decision should not run")


def _gate_stage(
    prefilter: PlannerPrefilter | None,
    *,
    config: OrchestratorConfig,
) -> GateStage:
    registry = ChatIgnoreRegistry()
    return GateStage(
        TurnPlanner(use_llm=False),
        NoDecision(),
        prefilter,
        config,
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        registry,
    )


@pytest.mark.asyncio
async def test_gate_stage_prefilter_skips_planner():
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=True,
    )
    registry = ChatIgnoreRegistry()
    prefilter = PlannerPrefilter(
        ReplyEligibility(
            IntentDetector(bot_names=["vanessa"]),
            TriggerKeywordChecker(keywords=[]),
            NoiseFilter(),
            registry,
            post_reply_listen_count=3,
            post_reply_listen_idle_seconds=300.0,
        )
    )
    gate = _gate_stage(prefilter, config=config)
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
