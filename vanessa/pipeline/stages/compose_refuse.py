import logging

from vanessa.config.content import get_photo_placeholder
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.decision.repeated_question import is_repeated_message
from vanessa.pipeline.llm.format.answer_tag import (
    extract_ignore_reason,
    has_ignore_marker,
)

logger = logging.getLogger("vanessa.pipeline.stages")


class _ComposeRefuseMixin:
    def _should_refuse_repeat(self, ctx: TurnPipelineContext) -> bool:
        # Compose-stage refusal, defense-in-depth for spam: the gate usually
        # catches repeats, but some paths never run the decision engine (the
        # vision forced-turn path) or could be bypassed in the future. Skip
        # when the planner explicitly asked to reply — a poker "чек" is a
        # legitimate repeat. Otherwise refuse before the expensive LLM.
        # A bare caption-less photo carries only the placeholder ("[фото]") — not
        # real content — so two consecutive photos must never be mistaken for a
        # repeated-message spam burst (they normalize to the same token). The
        # repeat check still applies to captioned photos and text.
        if not self._refuse_enabled:
            return False
        if (
            ctx.turn.has_image
            and ctx.turn.message.strip() == get_photo_placeholder()
        ):
            return False
        if ctx.turn_plan is not None and ctx.turn_plan.should_reply is True:
            return False
        return is_repeated_message(
            ctx.turn.message,
            ctx.recent,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            min_occurrences=self._refuse_min_occurrences,
        )

    def _refuse_after_generate(self, ctx: TurnPipelineContext) -> bool | None:
        # The compose model is instructed to output the tag `[ignore]` (plus an
        # optional short debug-only reason after it — never an `[answer]` or a
        # message) when the user repeats the same thing — an explicit refusal
        # signal, far more robust than an empty reply. Honor it here (at the
        # moment of preparing the answer) instead of letting it flow through as
        # a literal `[ignore]` message.
        if self._refuse_enabled and has_ignore_marker(ctx.reply or ""):
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_marker",
                # The model writes a short reason after the tag (e.g.
                # `[ignore] повтор того же вопроса`) purely for debugging — it
                # is never delivered to the chat.
                detail=extract_ignore_reason(ctx.reply),
            )
        # Fallback: an empty reply is also treated as the model staying silent
        # (older prompt / the model forgetting the marker). Previously an empty
        # reply still created an empty assistant message and a recorded REPLY
        # turn — the bot "replied" with nothing while believing it answered.
        if self._refuse_enabled and not (ctx.reply or "").strip():
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_empty",
            )
        return None

    def _refuse(
        self,
        ctx: TurnPipelineContext,
        *,
        reason: str,
        log_event: str,
        detail: str = "",
    ) -> bool:
        """Refuse the answer at compose time.

        Drops the (already generated or never-started) reply and returns False so
        the orchestrator finalizes the turn as an IGNORE via ``FinalizeStage.skip``
        — the user message is still indexed, no assistant message is created and
        nothing is delivered to the chat. ``detail`` is an optional extra debug
        context (e.g. the model's reason written after the ``[ignore]`` marker);
        it is only logged, never sent anywhere.
        """
        ctx.reply = None
        ctx.refuse_reason = reason
        logger.info(
            "%s request_id=%s reason=%s ignore_reason=%r sender_id=%s text=%r",
            log_event,
            get_request_id(),
            reason,
            detail,
            ctx.turn.sender_telegram_id,
            ctx.turn.message,
        )
        return False
