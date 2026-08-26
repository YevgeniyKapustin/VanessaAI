import logging
import time

from app.core.protocols import LLMProviderProtocol
from app.core.request_context import get_request_id
from app.llm.humor.critic import CriticVerdict, HumorCritic
from app.llm.prompts.session_format import session_context_messages
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext

logger = logging.getLogger(__name__)


class CritiqueStage:
    """Generator–Critic loop for humor turns.

    Reviews the composed draft with the Critic agent. On REJECTED the draft is
    sent back to the generator together with the critic's fix instruction, up
    to ``critic_max_iterations`` fixes. On the last rejected iteration the
    latest draft is shipped anyway (fail-open — never block a reply).
    """

    def __init__(
        self,
        llm: LLMProviderProtocol,
        critic: HumorCritic,
        config: OrchestratorConfig,
    ) -> None:
        self._llm = llm
        self._critic = critic
        self._config = config

    async def run(self, ctx: TurnPipelineContext) -> bool:
        assert ctx.reply is not None
        if not self._enabled_for(ctx):
            return True

        started = time.perf_counter()
        draft = ctx.reply
        max_fixes = max(0, self._config.critic_max_iterations)

        for attempt in range(max_fixes + 1):
            ctx.critic_iterations = attempt + 1
            verdict = await self._critic.review(
                draft,
                user_message=ctx.turn.message,
                humor_quotes=ctx.humor_quotes,
            )
            ctx.critic_verdict = verdict

            if verdict.approved:
                break

            if attempt >= max_fixes:
                logger.info(
                    "humor_critic rejected at max iterations, shipping draft "
                    "request_id=%s score=%s",
                    get_request_id(),
                    verdict.score,
                )
                break

            fix = verdict.fix_instruction or verdict.reason
            logger.info(
                "humor_critic rejected, regenerating with feedback "
                "request_id=%s score=%s",
                get_request_id(),
                verdict.score,
            )
            draft = await self._llm.generate(
                user_message=ctx.turn.message,
                context_blocks=ctx.context_blocks,
                session_messages=session_context_messages(ctx.recent),
                humor_quotes=ctx.humor_quotes or None,
                sender_telegram_id=ctx.turn.sender_telegram_id,
                sender_name=ctx.sender_name,
                critic_feedback=fix,
            )

        ctx.reply = draft
        ctx.critic_ms = (time.perf_counter() - started) * 1000

        verdict = ctx.critic_verdict
        assert verdict is not None
        logger.info(
            "turn_stage critique request_id=%s status=%s score=%s "
            "iterations=%s critic_ms=%.1f",
            get_request_id(),
            verdict.status.value,
            verdict.score,
            ctx.critic_iterations,
            ctx.critic_ms,
        )
        return True

    def _enabled_for(self, ctx: TurnPipelineContext) -> bool:
        if not self._config.critic_enabled:
            return False
        if self._config.critic_apply_to_all:
            return True
        # Default: critique only turns where humor quotes were actually used.
        return bool(ctx.humor_quotes)
