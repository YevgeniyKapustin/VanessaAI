import app.decision  # noqa: F401  (import-order guard for a pre-existing circular import)

import pytest

from app.core.turn import ChatTurnInput
from app.llm.humor.critic import CriticStatus, CriticVerdict
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.pipeline.critique_stage import CritiqueStage


class FakeLLM:
    def __init__(self, reply: str = "fixed reply") -> None:
        self.reply = reply
        self.calls: list[str | None] = []

    async def generate(
        self,
        user_message: str,
        context_blocks: list,
        session_messages: list | None = None,
        humor_quotes: list[str] | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
        critic_feedback: str | None = None,
        tone: str | None = None,
    ) -> str:
        self.calls.append(critic_feedback)
        return self.reply


class ScriptedCritic:
    def __init__(self, *verdicts: CriticVerdict) -> None:
        self._verdicts = list(verdicts)
        self.reviews: list[tuple[str, list[str]]] = []

    async def review(self, draft: str, *, user_message: str, humor_quotes: list[str]) -> CriticVerdict:
        self.reviews.append((draft, humor_quotes))
        return self._verdicts.pop(0)


def _config(*, critic_enabled: bool = True, max_iterations: int = 1, apply_to_all: bool = False) -> OrchestratorConfig:
    return OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=5,
        planner_prefilter_enabled=False,
        critic_enabled=critic_enabled,
        critic_max_iterations=max_iterations,
        critic_apply_to_all=apply_to_all,
    )


def _ctx(message: str = "ну ладно поработаю", humor_quotes: list[str] | None = None) -> TurnPipelineContext:
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-1001,
            message=message,
            sender_telegram_id=42,
        )
    )
    ctx.reply = "draft reply"
    ctx.humor_quotes = humor_quotes or []
    ctx.recent = []
    ctx.context_blocks = []
    return ctx


@pytest.mark.asyncio
async def test_critique_approve_no_regeneration():
    llm = FakeLLM()
    critic = ScriptedCritic(CriticVerdict(status=CriticStatus.APPROVED, score=4, reason="ок"))
    stage = CritiqueStage(llm, critic, _config())

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is True

    assert ctx.reply == "draft reply"
    assert llm.calls == []
    assert ctx.critic_iterations == 1
    assert ctx.critic_verdict is not None
    assert ctx.critic_verdict.approved is True


@pytest.mark.asyncio
async def test_critique_reject_then_approve_regenerates_once():
    llm = FakeLLM(reply="fixed reply")
    critic = ScriptedCritic(
        CriticVerdict(
            status=CriticStatus.REJECTED,
            score=2,
            reason="плоско",
            fix_instruction="добавь иронию",
        ),
        CriticVerdict(status=CriticStatus.APPROVED, score=4, reason="теперь ок"),
    )
    stage = CritiqueStage(llm, critic, _config(max_iterations=1))

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is True

    assert ctx.reply == "fixed reply"
    assert llm.calls == ["добавь иронию"]
    assert ctx.critic_iterations == 2
    assert ctx.critic_verdict is not None
    assert ctx.critic_verdict.approved is True


@pytest.mark.asyncio
async def test_critique_no_reply_stops_without_reply():
    llm = FakeLLM()
    critic = ScriptedCritic(
        CriticVerdict(
            status=CriticStatus.NO_REPLY,
            score=3,
            reason="вопрос риторический",
        ),
    )
    stage = CritiqueStage(llm, critic, _config())

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is False

    assert ctx.reply is None
    assert llm.calls == []
    assert ctx.critic_iterations == 1
    assert ctx.critic_verdict is not None
    assert ctx.critic_verdict.no_reply is True


@pytest.mark.asyncio
async def test_critique_reject_on_last_iteration_ships_draft():
    llm = FakeLLM(reply="fixed reply")
    critic = ScriptedCritic(
        CriticVerdict(
            status=CriticStatus.REJECTED,
            score=1,
            reason="ещё хуже",
            fix_instruction="сделай лучше",
        ),
        CriticVerdict(status=CriticStatus.REJECTED, score=1, reason="снова мимо"),
    )
    stage = CritiqueStage(llm, critic, _config(max_iterations=1))

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is True

    # latest draft is shipped despite the final REJECTED (fail-open)
    assert ctx.reply == "fixed reply"
    assert llm.calls == ["сделай лучше"]
    assert ctx.critic_iterations == 2
    assert ctx.critic_verdict is not None
    assert ctx.critic_verdict.approved is False


@pytest.mark.asyncio
async def test_critique_zero_iterations_rejects_without_regen():
    llm = FakeLLM(reply="fixed reply")
    critic = ScriptedCritic(
        CriticVerdict(status=CriticStatus.REJECTED, score=1, reason="мимо"),
    )
    stage = CritiqueStage(llm, critic, _config(max_iterations=0))

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is True

    assert ctx.reply == "draft reply"
    assert llm.calls == []
    assert ctx.critic_iterations == 1


@pytest.mark.asyncio
async def test_critique_disabled_passthrough():
    llm = FakeLLM()
    critic = ScriptedCritic(CriticVerdict(status=CriticStatus.APPROVED, score=5))
    stage = CritiqueStage(llm, critic, _config(critic_enabled=False))

    ctx = _ctx(humor_quotes=["найди работу"])
    assert await stage.run(ctx) is True

    assert ctx.reply == "draft reply"
    assert critic.reviews == []
    assert ctx.critic_verdict is None


@pytest.mark.asyncio
async def test_critique_humor_only_scope_skips_non_humor_turns():
    llm = FakeLLM()
    critic = ScriptedCritic(CriticVerdict(status=CriticStatus.APPROVED, score=5))
    stage = CritiqueStage(llm, critic, _config())

    ctx = _ctx(humor_quotes=[])
    assert await stage.run(ctx) is True

    assert critic.reviews == []
    assert ctx.critic_verdict is None


@pytest.mark.asyncio
async def test_critique_apply_to_all_overrides_humor_scope():
    llm = FakeLLM()
    critic = ScriptedCritic(CriticVerdict(status=CriticStatus.APPROVED, score=5))
    stage = CritiqueStage(llm, critic, _config(apply_to_all=True))

    ctx = _ctx(humor_quotes=[])
    assert await stage.run(ctx) is True

    assert len(critic.reviews) == 1
    assert ctx.critic_verdict is not None
