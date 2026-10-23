from unittest.mock import AsyncMock

from vanessa.core.turn import ChatTurnInput
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.stages.compose import _compose_generate_request
from vanessa.pipeline.stages.retrieve import RetrieveStage
from vanessa.pipeline.stages.retrieve_pinned import run_pinned_step

BLOCK = KnowledgeBlock(
    path="People/team.md",
    title="Команда",
    kind="note",
    content="## Состав\n  - Боб — девопс",
)


def _ctx() -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="кто у нас девопс?",
            sender_telegram_id=42,
        )
    )
    ctx.turn_plan = TurnPlan(original="x", text="", skip_search=True)
    return ctx


def _pinned(blocks=None, error: Exception | None = None) -> AsyncMock:
    pinned = AsyncMock()
    pinned.blocks.return_value = blocks or []
    pinned.blocks.side_effect = error
    return pinned


async def test_pinned_step_adds_blocks() -> None:
    ctx = _ctx()
    await run_pinned_step(ctx, _pinned([BLOCK]))
    assert ctx.knowledge_blocks == [BLOCK]


async def test_pinned_step_off_or_failing_keeps_turn() -> None:
    ctx = _ctx()
    await run_pinned_step(ctx, None)
    await run_pinned_step(ctx, _pinned(error=RuntimeError("db down")))
    assert ctx.knowledge_blocks == []


async def test_retrieve_stage_puts_pinned_note_in_compose_prompt() -> None:
    ctx = _ctx()
    stage = RetrieveStage(None, pinned_notes=_pinned([BLOCK]))
    assert await stage.run(ctx) is True
    request = _compose_generate_request(
        ctx,
        session_messages=[],
        metrics_block=None,
        attitude_note=None,
        images=None,
        photo_candidates=None,
    )
    prompt = PromptBuilder().build_user_prompt(request)
    assert "From my archive on the topic:" in prompt
    assert "Боб — девопс" in prompt
