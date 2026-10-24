"""Tests for the Hermes ask directive in the compose prompt."""

from vanessa.config.content import get_content
from vanessa.core.messages import ContextMessage
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.stages.compose import _compose_generate_request


def _prompt(hermes_status: str | None) -> str:
    return PromptBuilder().build_user_prompt(
        "что с MR 42?", [], hermes_status=hermes_status
    )


def test_asked_note_rendered() -> None:
    llm = get_content().llm
    prompt = _prompt("asked")
    assert llm.hermes_asked_note.strip()
    assert llm.hermes_asked_note.strip() in prompt
    assert llm.hermes_offline_note.strip() not in prompt


def test_offline_note_rendered() -> None:
    llm = get_content().llm
    prompt = _prompt("offline")
    assert llm.hermes_offline_note.strip()
    assert llm.hermes_offline_note.strip() in prompt
    assert llm.hermes_asked_note.strip() not in prompt


def test_no_note_without_status() -> None:
    llm = get_content().llm
    prompt = _prompt(None)
    assert llm.hermes_asked_note.strip() not in prompt
    assert llm.hermes_offline_note.strip() not in prompt


def test_unknown_status_renders_nothing() -> None:
    llm = get_content().llm
    prompt = _prompt("weird")
    assert llm.hermes_asked_note.strip() not in prompt


def test_compose_request_carries_hermes_status() -> None:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(telegram_chat_id=1, message="m", sender_telegram_id=2)
    )
    ctx.turn_plan = TurnPlan(original="m", text="", skip_search=True)
    ctx.hermes_status = "asked"
    request = _compose_generate_request(
        ctx,
        session_messages=[],
        metrics_block=None,
        attitude_note=None,
        images=None,
        photo_candidates=None,
    )
    assert request.hermes_status == "asked"


def test_none_note_without_status() -> None:
    llm = get_content().llm
    assert llm.hermes_none_note.strip()
    assert llm.hermes_none_note.strip() in _prompt(None)
    assert llm.hermes_none_note.strip() not in _prompt("asked")


def test_retry_note_only_on_retry() -> None:
    note = get_content().llm.false_promise_retry_note.strip()
    builder = PromptBuilder()
    retry = builder.build_user_prompt("что я делал?", [], false_promise_retry=True)
    assert note
    assert note in retry
    assert note not in _prompt(None)


def test_earlier_thread_rendered_with_header() -> None:
    llm = get_content().llm
    earlier = [
        ContextMessage(id=1, role="assistant", content="Ща гляну… скину списком")
    ]
    prompt = PromptBuilder().build_user_prompt(
        "ты обещала мне список", [], earlier_messages=earlier
    )
    assert llm.earlier_header in prompt
    assert "скину списком" in prompt
    assert llm.earlier_header not in _prompt(None)
