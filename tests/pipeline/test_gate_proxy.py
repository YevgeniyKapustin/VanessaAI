"""Gate accepts proxy questions and the owner's DM where bots are filtered."""

import pytest

from vanessa.config.settings import settings
from vanessa.core.messages import StoredMessage
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionAction, DecisionReason
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages import GateStage
from vanessa.pipeline.turn_metrics import TurnMetrics

OWNER = 999
BOT = 777


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


def _gate(planner: FakePlanner) -> GateStage:
    return GateStage(
        planner,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,
        _config(),
        TurnMetrics(),
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )


def _ctx(turn: ChatTurnInput) -> TurnPipelineContext:
    return TurnPipelineContext(
        turn=turn,
        user_msg=StoredMessage(id=1, role="user", content=turn.message),
        session=ChatSessionState(
            messages=[],
            in_listen_window=False,
            idle_since_last_bot_seconds=None,
            idle_expired=False,
            has_recent_dismissal=False,
        ),
    )


def _question_turn(**overrides) -> ChatTurnInput:
    values = {
        "telegram_chat_id": -1001,
        "message": "Евгений, когда будет релиз?",
        "sender_telegram_id": BOT,
        "sender_first_name": "Agent",
        "chat_title": "Work chat",
        "chat_type": "supergroup",
        "sender_is_bot": True,
        "reply_to_sender_telegram_id": OWNER,
    }
    values.update(overrides)
    return ChatTurnInput(**values)


@pytest.mark.asyncio
async def test_proxy_question_reaches_the_planner(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")
    planner = FakePlanner()

    with pytest.raises(PlannerCalledError):
        await _gate(planner).run(_ctx(_question_turn()))

    assert planner.calls == 1


@pytest.mark.asyncio
async def test_side_bot_chat_still_stops_before_the_planner(monkeypatch) -> None:
    monkeypatch.setattr(settings, "proxy_chat_titles", "work")
    planner = FakePlanner()
    ctx = _ctx(_question_turn(message="Евгений, я всё сделал"))

    assert await _gate(planner).run(ctx) is False

    assert planner.calls == 0
    assert ctx.result is not None
    assert ctx.result.action == DecisionAction.IGNORE.value
    assert ctx.result.reason == DecisionReason.BOT_PEER_SIDE.value


@pytest.mark.asyncio
async def test_owner_dm_reaches_the_planner(monkeypatch) -> None:
    monkeypatch.setattr(settings, "owner_dm_enabled", True)
    planner = FakePlanner()
    turn = _question_turn(
        telegram_chat_id=OWNER,
        chat_title=None,
        chat_type="private",
        sender_telegram_id=OWNER,
        sender_is_bot=False,
        sender_is_owner=True,
        message="давай в пятницу",
        reply_to_sender_telegram_id=None,
    )

    with pytest.raises(PlannerCalledError):
        await _gate(planner).run(_ctx(turn))

    assert planner.calls == 1
