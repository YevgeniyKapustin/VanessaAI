import pytest

from vanessa.core.messages import StoredMessage
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput
from vanessa.decision.gate.reaction_gate import ReactionGateResult
from vanessa.decision.models import DecisionAction, DecisionReason
from vanessa.rag.query_rewriter import QueryRewriter
from vanessa.services.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.services.pipeline.context import TurnPipelineContext
from vanessa.services.pipeline.stages import GateStage
from vanessa.services.turn_metrics import TurnMetrics


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


class FakeReactionGate:
    def __init__(self, respond: bool, reason: str = "no") -> None:
        self._respond = respond
        self._reason = reason
        self.calls: list[dict] = []

    async def evaluate(self, text, recent_messages, **kwargs):
        self.calls.append({"text": text, "recent": recent_messages, **kwargs})
        return ReactionGateResult(self._respond, self._reason)


def _config() -> OrchestratorConfig:
    return OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=False,
        defer_index_on_ignore=True,
    )


def _ctx(message: str = "смотрите какой кот") -> TurnPipelineContext:
    return TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message=message,
            sender_telegram_id=1,
        ),
        user_msg=StoredMessage(id=1, role="user", content=message),
        session=ChatSessionState(
            messages=[],
            in_listen_window=False,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )


@pytest.mark.asyncio
async def test_reaction_gate_no_finalizes_turn_without_planner():
    gate_classifier = FakeReactionGate(respond=False)
    indexing = FakeIndexing()
    gate = GateStage(
        QueryRewriter(use_llm=False),
        NoDecision(),
        None,
        _config(),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        indexing,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        reaction_gate=gate_classifier,  # type: ignore[arg-type]
    )
    ctx = _ctx()

    should_continue = await gate.run(ctx)

    assert should_continue is False
    assert len(gate_classifier.calls) == 1
    assert gate_classifier.calls[0]["text"] == "смотрите какой кот"
    assert gate_classifier.calls[0]["sender_telegram_id"] == 1
    assert ctx.planner_skipped is True
    assert ctx.turn_plan is None
    assert ctx.result is not None
    assert ctx.result.action == DecisionAction.IGNORE.value
    assert ctx.result.reason == DecisionReason.REACTION_GATE.value
    assert ctx.reaction_gate_ms > 0
    assert indexing.scheduled == [ctx.user_msg]


@pytest.mark.asyncio
async def test_reaction_gate_yes_proceeds_to_planner_and_decision():
    gate_classifier = FakeReactionGate(respond=True, reason="yes")
    gate = GateStage(
        QueryRewriter(use_llm=False),
        NoDecision(),
        None,
        _config(),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        reaction_gate=gate_classifier,  # type: ignore[arg-type]
    )
    ctx = _ctx()

    with pytest.raises(AssertionError, match="decision should not run"):
        await gate.run(ctx)

    # The reaction gate passed and the pipeline advanced past it to the planner.
    assert len(gate_classifier.calls) == 1
    assert ctx.turn_plan is not None


@pytest.mark.asyncio
async def test_reaction_gate_not_wired_is_skipped():
    gate = GateStage(
        QueryRewriter(use_llm=False),
        NoDecision(),
        None,
        _config(),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        FakeIndexing(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )
    ctx = _ctx()

    with pytest.raises(AssertionError, match="decision should not run"):
        await gate.run(ctx)

    assert ctx.reaction_gate_ms == 0.0
