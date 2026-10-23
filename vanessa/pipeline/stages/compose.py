import logging
import time

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.core.generate_request import GenerateRequest
from vanessa.core.messages import ContextMessage, ImageAttachment, PhotoCandidate
from vanessa.core.protocols import LLMProviderProtocol, MessageRepositoryProtocol
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.observability.tracing import get_tracer
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.llm.photo_request import is_photo_request
from vanessa.pipeline.llm.prompts.prompt_system import build_system_prompt
from vanessa.pipeline.llm.prompts.session_format import session_context_messages
from vanessa.pipeline.stages.compose_photos import _ComposePhotoMixin
from vanessa.pipeline.stages.compose_refuse import _ComposeRefuseMixin
from vanessa.pipeline.stages.photos import (
    _collect_photo_candidates,
    _collect_turn_images,
)

logger = logging.getLogger("vanessa.pipeline.stages")


def _compose_generate_request(
    ctx: TurnPipelineContext,
    *,
    session_messages: list[ContextMessage],
    metrics_block: str | None,
    attitude_note: str | None,
    images: list[ImageAttachment] | None,
    photo_candidates: list[PhotoCandidate] | None,
) -> GenerateRequest:
    turn = ctx.turn
    plan = ctx.turn_plan
    return GenerateRequest(
        user_message=turn.message,
        context_blocks=ctx.context_blocks,
        session_messages=session_messages,
        humor_quotes=ctx.humor_quotes or None,
        knowledge_blocks=ctx.knowledge_blocks or None,
        web_blocks=ctx.web_blocks or None,
        meme_blocks=(ctx.meme_blocks or None) if ctx.profile.stickers else None,
        meme_menu=(ctx.meme_menu or None) if ctx.profile.stickers else None,
        metrics_block=metrics_block,
        attitude_note=attitude_note,
        sender_telegram_id=turn.sender_telegram_id,
        sender_name=ctx.sender_name,
        tone=plan.tone,
        needs_clarification=plan.needs_clarification,
        clarification_hint=plan.clarification_hint,
        detail=plan.detail,
        uses_pro_model=plan.uses_pro_model,
        reply_to_text=turn.reply_to_text,
        reply_to_sender_telegram_id=turn.reply_to_sender_telegram_id,
        reply_to_sender_name=turn.reply_to_sender_name,
        images=images,
        photo_candidates=photo_candidates,
        # Current-message images render inside <msg> as <attachment> children so
        # the model never loses which photo goes with which caption. ``images``
        # (incl. prior-session vision) stays separate — it feeds the vision
        # model, not the current <msg>.
        current_images=list(turn.images) or None,
        scene_description=ctx.scene_description,
        hermes_status=ctx.hermes_status,
        schedule_note=ctx.schedule_note,
        channel_profile=ctx.profile,
        system_prompt=build_system_prompt(get_content(), profile=ctx.profile),
    )


class ComposeStage(_ComposeRefuseMixin, _ComposePhotoMixin):
    def __init__(
        self,
        llm: LLMProviderProtocol,
        *,
        refuse_enabled: bool = True,
        refuse_min_occurrences: int = 2,
        messages: MessageRepositoryProtocol | None = None,
    ) -> None:
        self._llm = llm
        self._refuse_enabled = refuse_enabled
        self._refuse_min_occurrences = max(2, refuse_min_occurrences)
        # Message repo used for the meaning-driven photo-album search
        # (``search_photo_messages``): finds photo messages whose caption matches
        # the MEANING of the turn, not the literal text the user typed.
        self._messages = messages

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if self._should_refuse_repeat(ctx):
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_repeated",
            )

        llm_started = time.perf_counter()
        session_messages = session_context_messages(ctx.recent)
        tracer = get_tracer()
        async with tracer.span(
            name="compose:inject_knowledge",
            input=[
                {
                    "path": block.path,
                    "kind": block.kind,
                    "title": block.title,
                    "chars": len(block.content or ""),
                }
                for block in ctx.knowledge_blocks
            ],
        ):
            pass
        metrics_block, attitude_note = self._feedback_notes(ctx)
        # Vision: attach the current + recent-session images when enabled; the
        # provider routes the call to the vision model only when images are present.
        images = _collect_turn_images(ctx) if settings.vision_enabled else []
        # Did the user explicitly ask for a photo? Drives the honesty directives
        # (marker required / honest refusal) and the missed-request metric below.
        photo_requested = is_photo_request(ctx.turn.message)
        photo_messages = await self._meaning_photo_messages(ctx)
        photo_candidates = (
            _collect_photo_candidates(ctx, photo_messages)
            if settings.vision_enabled
            else []
        )
        ctx.reply = await self._llm.generate(
            _compose_generate_request(
                ctx,
                session_messages=session_messages,
                metrics_block=metrics_block,
                attitude_note=attitude_note,
                images=images or None,
                photo_candidates=photo_candidates or None,
            )
        )
        refused = self._refuse_after_generate(ctx)
        if refused is not None:
            return refused
        photo_index = self._apply_photo_index(ctx, photo_candidates)
        self._record_photo_outcome(
            ctx,
            photo_requested=photo_requested,
            photo_index=photo_index,
            photo_candidates=photo_candidates,
        )
        ctx.llm_ms = (time.perf_counter() - llm_started) * 1000
        logger.info(
            "turn_stage llm request_id=%s reply_len=%s llm_ms=%.1f",
            get_request_id(),
            len(ctx.reply),
            ctx.llm_ms,
        )
        return True
