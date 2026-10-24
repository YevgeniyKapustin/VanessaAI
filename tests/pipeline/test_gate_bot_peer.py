import pytest

from vanessa.core.messages import ContextMessage, StoredMessage
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.bot_peer_budget import BotPeerBudget, BotPeerLimits
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages import GateStage
from vanessa.pipeline.stages.bot_peer import record_bot_peer_reply
from vanessa.pipeline.turn_metrics import TurnMetrics

KIRILL = 777
HUMAN = 1
DEPTH = 3


class PlannerCalledError(Exception):
    pass


class FakePlanner:
    def __init__(self) -> None:
        self.calls = 0

    async def prepare(self, *args, **kwargs):
        _ = args, kwargs
        self.calls += 1
        raise PlannerCalledError


def _config() -> OrchestratorConfig:
    return OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=3,
        planner_prefilter_enabled=False,
    )


def _ctx(
    *,
    sender: int = KIRILL,
    is_bot: bool = True,
    mentions_bot: bool = False,
    listen: bool = False,
    recent: list[ContextMessage] | None = None,
) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="ну что скажешь",
            sender_telegram_id=sender,
            sender_first_name="Kirill",
            sender_is_bot=is_bot,
            mentions_bot=mentions_bot,
        ),
        user_msg=StoredMessage(id=1, role="user", content="ну что скажешь"),
        session=ChatSessionState(
            messages=[],
            in_listen_window=listen,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )
    ctx.recent = recent or []
    return ctx


def _gate(planner: FakePlanner, budget: BotPeerBudget) -> GateStage:
    return GateStage(
        planner,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,
        _config(),
        TurnMetrics(),
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        bot_budget=budget,
    )


def _budget() -> BotPeerBudget:
    return BotPeerBudget(BotPeerLimits(max_in_row=3, cooldown_seconds=0))


def _talk(partner: int) -> list[ContextMessage]:
    return [
        ContextMessage(id=1, role="user", content="привет", sender_telegram_id=partner),
        ContextMessage(id=2, role="assistant", content="хай"),
    ]


@pytest.mark.asyncio
async def test_non_addressed_bot_message_never_calls_planner():
    planner = FakePlanner()
    ctx = _ctx()

    assert await _gate(planner, _budget()).run(ctx) is False

    assert planner.calls == 0
    assert ctx.planner_skipped is True
    assert ctx.result is not None
    assert ctx.result.action == DecisionAction.IGNORE.value
    assert ctx.result.reason == DecisionReason.BOT_PEER_SIDE.value


@pytest.mark.asyncio
async def test_bot_in_listen_window_of_its_own_talk_reaches_planner():
    planner = FakePlanner()
    with pytest.raises(PlannerCalledError):
        await _gate(planner, _budget()).run(_ctx(listen=True, recent=_talk(KIRILL)))


@pytest.mark.asyncio
async def test_listen_window_of_other_partner_stops_bot():
    planner = FakePlanner()
    ctx = _ctx(listen=True, recent=_talk(HUMAN))
    assert await _gate(planner, _budget()).run(ctx) is False
    assert planner.calls == 0


@pytest.mark.asyncio
async def test_reply_loop_with_bot_stops_at_depth_then_human_resets():
    planner = FakePlanner()
    budget = _budget()
    gate = _gate(planner, budget)
    for _ in range(DEPTH):
        ctx = _ctx(mentions_bot=True)
        with pytest.raises(PlannerCalledError):
            await gate.run(ctx)
        record_bot_peer_reply(budget, ctx)

    stopped = _ctx(mentions_bot=True)
    assert await gate.run(stopped) is False
    assert stopped.result.reason == DecisionReason.BOT_PEER_LIMIT.value
    assert planner.calls == DEPTH

    with pytest.raises(PlannerCalledError):
        await gate.run(_ctx(sender=HUMAN, is_bot=False))
    with pytest.raises(PlannerCalledError):
        await gate.run(_ctx(mentions_bot=True))


def test_hermes_follow_up_counts_as_second_reply():
    budget = BotPeerBudget(BotPeerLimits(max_in_row=2, cooldown_seconds=0))
    ctx = _ctx(mentions_bot=True)
    ctx.hermes_status = "asked"
    record_bot_peer_reply(budget, ctx)
    assert budget.blocked_reason("telegram:-100", KIRILL) == "depth"


def test_reply_to_human_is_not_counted():
    budget = BotPeerBudget(BotPeerLimits(max_in_row=1, cooldown_seconds=0))
    record_bot_peer_reply(budget, _ctx(sender=HUMAN, is_bot=False))
    assert budget.allows("telegram:-100", HUMAN)
