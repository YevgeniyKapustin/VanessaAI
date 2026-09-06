import logging

from vanessa.config.content import get_photo_placeholder
from vanessa.config.settings import settings
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import (
    DecisionAction,
    DecisionReason,
    DecisionResult,
)
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.gate_support import finish_ignore_turn

logger = logging.getLogger("vanessa.pipeline.stages")


class _GateVisionMixin:
    async def _load_sender_profile(self, ctx: TurnPipelineContext) -> None:
        if self._metrics_retriever is None:
            return
        try:
            ctx.sender_profile = await self._metrics_retriever.get_by_telegram_id(
                ctx.turn.sender_telegram_id
            )
        except Exception:
            logger.exception("metrics_retrieve_failed")
            ctx.sender_profile = None

    async def _gate_bare_photo(self, ctx: TurnPipelineContext) -> bool | None:
        # Bare caption-less photo ("[фото]" placeholder): Vanessa is NOT obliged
        # to reply to every photo, and a photo she does not answer is not even
        # analyzed (never sent to the vision model). She responds to a bare photo
        # only when she is actively listening (recently talked with her —
        # ``in_listen_window``) or the photo is addressed to her (a reply to her
        # message / a mention). Otherwise the turn is finalized as an IGNORE here,
        # before any prefilter/planner/vision cost.
        if not ctx.turn.has_image or not settings.vision_enabled:
            return None
        # Rollback toggle: restore the old "reply to ANY photo" behavior.
        if settings.vision_reply_to_any_photo:
            return await self._force_vision_turn(ctx)
        if ctx.turn.message.strip() != get_photo_placeholder():
            return None
        # Captioned photos flow through the normal gate pipeline (prefilter,
        # reaction gate, planner, decision engine) like any text message — the
        # caption is real content. Only when the pipeline decides REPLY does the
        # compose stage attach the image to the vision model.
        return await self._resolve_bare_photo(ctx)

    async def _resolve_bare_photo(self, ctx: TurnPipelineContext) -> bool:
        assert ctx.session is not None
        addressed = ctx.session.in_listen_window
        if ctx.turn.mentions_bot or ctx.turn.reply_to_bot:
            addressed = True
        if addressed:
            return await self._force_vision_turn(ctx)
        await finish_ignore_turn(
            ctx,
            reason=DecisionReason.NOT_EXPECTED.value,
            metrics=self._metrics,
            indexing=self._indexing,
            config=self._config,
            planner_skipped=True,
            log_event="turn_stage bare_photo_not_addressed",
        )
        return False

    async def _force_vision_turn(self, ctx: TurnPipelineContext) -> bool:
        """Vision reply path for a bare photo the gate decided to answer.

        Called only when Vanessa is actively listening (``in_listen_window``) or
        the photo is addressed to her (a reply to her message / a mention), or
        when the ``vision_reply_to_any_photo`` rollback toggle is on. Skips the
        text planner (a bare photo has nothing useful to classify) and builds a
        forced ``TurnPlan`` + REPLY ``DecisionResult`` so the turn proceeds to
        Retrieve/Compose, where the vision model describes the image.
        ``FinalizeStage`` asserts a non-None decision, so the forced decision is
        required here.
        """
        if self._metrics_retriever is not None:
            try:
                ctx.sender_profile = await self._metrics_retriever.get_by_telegram_id(
                    ctx.turn.sender_telegram_id
                )
            except Exception:
                logger.exception("metrics_retrieve_failed")
                ctx.sender_profile = None
        message = ctx.turn.message.strip()
        ctx.turn_plan = TurnPlan(
            original=ctx.turn.message,
            text=message or "(описание фото)",
            skip_search=True,
            should_reply=True,
        )
        ctx.decision = DecisionResult(
            action=DecisionAction.REPLY,
            reason=DecisionReason.FORCE_REPLY,
            relevance_score=1.0,
        )
        ctx.plan_ms = 0.0
        ctx.decision_ms = 0.0
        logger.info(
            "turn_stage vision_forced request_id=%s chat_id=%s text=%r images=%s",
            get_request_id(),
            ctx.turn.telegram_chat_id,
            ctx.turn.message,
            len(ctx.turn.images),
        )
        return True
