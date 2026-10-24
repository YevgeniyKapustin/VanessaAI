"""The planner knows the owner and routes his own work activity to Hermes."""

from datetime import UTC, datetime

import pytest

from tests.pipeline.test_gate_side_talk import FakeMessageRepo, _build_engine
from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage, StoredMessage
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.gate.eligibility.user_ignore import ChatIgnoreRegistry
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.turn_planner import TurnPlanner
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.stages import GateStage
from vanessa.pipeline.turn_metrics import TurnMetrics

_OWNER_ID = 777
_PLAN_JSON = (
    '{"should_reply": true, "search_query": "", "skip": false, '
    '"ask_hermes": true, "hermes_query": "что владелец сделал сегодня"}'
)


async def _planner_prompt(*, owner: bool) -> str:
    captured: dict[str, str] = {}

    class _Client:
        async def complete(self, model, messages, kind, **kwargs):
            _ = model, kind, kwargs
            captured["prompt"] = messages[0]["content"]
            return _PLAN_JSON

    planner = TurnPlanner(use_llm=True, llm_client=_Client())
    plan = await planner.prepare(
        "ванесса что я делал сегодня", sender_name="Евгений", sender_is_owner=owner
    )
    assert plan.ask_hermes is True
    return captured["prompt"]


@pytest.mark.asyncio
async def test_prompt_marks_owner_sender() -> None:
    prompt = await _planner_prompt(owner=True)
    assert "Sender is the owner: yes" in prompt
    assert "{sender_is_owner}" not in prompt


@pytest.mark.asyncio
async def test_prompt_marks_other_sender() -> None:
    assert "Sender is the owner: no" in await _planner_prompt(owner=False)


def test_prompt_has_one_work_lookup_rule_before_decisions() -> None:
    prompt = get_content().rag.turn_planner_prompt
    rule = prompt.index("## Work lookup (Hermes)")
    assert rule < prompt.index("## Decision order")
    block = prompt[rule : prompt.index("## Decision order")]
    assert "for ANY sender" in block
    assert "In doubt between a memory search and Hermes" in block
    assert "never replaces Hermes for a" in block
    assert "«чем я вчера занимался»" in block
    assert "ask_hermes=false: chit-chat" in block


def test_prompt_keeps_query_rules() -> None:
    prompt = get_content().rag.turn_planner_prompt
    assert "{sender_is_owner}" in prompt
    assert "A reminder of a work lookup Vanessa promised earlier" in prompt
    assert "FIND it and give its" in prompt
    assert "Sender is the owner: no → the same words" not in prompt


class CapturingPlanner:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def prepare(self, *args: object, **kwargs: object) -> TurnPlan:
        _ = args
        self.kwargs = kwargs
        return TurnPlan(
            original="x", text="", skip_search=True, should_reply=True
        )


@pytest.mark.asyncio
async def test_gate_passes_owner_flag_and_earlier_thread(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", _OWNER_ID)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", "")
    when = datetime(2026, 10, 24, 0, 54, tzinfo=UTC)
    earlier = [
        ContextMessage(
            id=1, role="assistant", content="скину списком", created_at=when
        )
    ]
    planner = CapturingPlanner()
    gate = GateStage(
        planner,  # type: ignore[arg-type]
        _build_engine(),
        None,
        OrchestratorConfig(
            session_window_size=10,
            session_idle_seconds=300.0,
            post_reply_listen_count=3,
            planner_prefilter_enabled=False,
        ),
        TurnMetrics(),
        FakeMessageRepo(),  # type: ignore[arg-type]
        ChatIgnoreRegistry(),
    )
    session = ChatSessionState(
        messages=[],
        in_listen_window=False,
        idle_since_last_bot_seconds=None,
        idle_expired=False,
        has_recent_dismissal=False,
        earlier_messages=earlier,
    )
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="ванесса ты обещала мне список",
            sender_telegram_id=_OWNER_ID,
            mentions_bot=True,
        ),
        user_msg=StoredMessage(id=2, role="user", content="x"),
        session=session,
    )

    await gate.run(ctx)

    assert planner.kwargs["sender_is_owner"] is True
    assert planner.kwargs["recent_messages"] == earlier
