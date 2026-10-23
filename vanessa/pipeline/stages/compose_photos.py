import logging

from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage, PhotoCandidate, stored_to_context
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.observability.metrics import (
    record_photo_request_missed,
    record_photo_send,
)
from vanessa.knowledge.metrics.feedback import (
    render_annoyance_note,
    render_feedback_block,
)
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.llm.format.photo_tag import extract_photo_index

logger = logging.getLogger("vanessa.pipeline.stages")


def _photo_query(turn_plan, message: str) -> str:
    """Prefer the planner archive query, then the planner query, then raw."""
    for candidate in (turn_plan.knowledge_query, turn_plan.text):
        if candidate and candidate.strip():
            return candidate.strip()
    return message.strip()


class _ComposePhotoMixin:
    def _feedback_notes(self, ctx: TurnPipelineContext):
        # The notes must name the sender EXACTLY as the current <msg sender="...">
        # does (ctx.sender_name — the same resolved display name), so the model
        # never has to reconcile two different names for one person (e.g. the
        # profile name vs a casual self-reference in the message) and burns
        # chain-of-thought guessing who the sender is.
        metrics_block = None
        if ctx.sender_profile is not None and ctx.sender_metrics is not None:
            metrics_block = render_feedback_block(
                name=ctx.sender_name,
                metrics=ctx.sender_metrics,
                mood=ctx.sender_profile.mood,
            )
        # Cold-reply note: a sender stuck in a same-topic loop gets a dry, sharp,
        # brief answer — no warmth, no fluff (the loop dropped Vanessa's attitude).
        attitude_note = None
        if (
            ctx.sender_profile is not None
            and ctx.annoyance >= settings.feedback_annoyance_threshold
        ):
            attitude_note = render_annoyance_note(
                name=ctx.sender_name,
                annoyance=ctx.annoyance,
            )
        return metrics_block, attitude_note

    def _photo_search_ready(self, ctx: TurnPipelineContext) -> bool:
        if not settings.vision_enabled or self._messages is None:
            return False
        if not ctx.profile.photos:
            return False
        return ctx.turn_plan is not None

    async def _meaning_photo_messages(
        self, ctx: TurnPipelineContext
    ) -> list[ContextMessage]:
        # Photo album: photos the bot could re-send, matched to the context by
        # caption full-text search + the recent session. The dedicated meaning-search leg
        # (``search_photo_messages``) finds photo messages whose caption matches
        # the REWRITTEN query — so a bare photo is found by the MEANING of the
        # turn ("скинь то фото где кот" -> the caption "рыжий кот на диване"),
        # not by the literal words the user typed. Fail-open: a search error
        # must never block the reply. The current turn's own photos are excluded
        # inside ``_collect_photo_candidates`` (they are already attached).
        if not self._photo_search_ready(ctx):
            return []
        assert ctx.turn_plan is not None
        meaning_query = _photo_query(ctx.turn_plan, ctx.turn.message)
        try:
            stored = await self._messages.search_photo_messages(
                meaning_query,
                limit=settings.vision_photo_candidates * 2,
            )
            return [stored_to_context(m) for m in stored]
        except Exception:
            logger.exception(
                "photo_meaning_search_failed request_id=%s query=%r",
                get_request_id(),
                meaning_query,
            )
            return []

    def _apply_photo_index(
        self,
        ctx: TurnPipelineContext,
        photo_candidates: list[PhotoCandidate],
    ) -> int | None:
        # Resolve the [photo:<index>] marker the model may have emitted: strip it
        # from the reply and remember the file_id the bot should re-send.
        clean_reply, photo_index = extract_photo_index(ctx.reply)
        if photo_index is None:
            return None
        if 1 <= photo_index <= len(photo_candidates):
            candidate = photo_candidates[photo_index - 1]
            ctx.photo_file_id = candidate.telegram_file_id
            # Carry the stored bytes so the bot can fall back to an upload
            # if the Telegram file_id is stale when it tries to re-send.
            ctx.photo_data_url = candidate.data_url
            logger.info(
                "photo_send_resolved request_id=%s index=%s file_id=%s",
                get_request_id(),
                photo_index,
                ctx.photo_file_id,
            )
        else:
            logger.warning(
                "photo_send_index_out_of_range request_id=%s index=%s total=%s",
                get_request_id(),
                photo_index,
                len(photo_candidates),
            )
        ctx.reply = clean_reply
        return photo_index

    def _record_photo_outcome(
        self,
        ctx: TurnPipelineContext,
        *,
        photo_requested: bool,
        photo_index: int | None,
        photo_candidates: list[PhotoCandidate],
    ) -> None:
        # Honesty + observability: a photo request that resolved to no delivery
        # is exactly the "сказала что отправила, но фото не пришло" bug. When the
        # user asked for a photo and we end up with no photo_file_id, record the
        # failure with a reason so it can be monitored and investigated.
        if ctx.photo_file_id:
            record_photo_send("resolved")
            return
        if not photo_requested:
            return
        reason = _missed_photo_reason(photo_index, photo_candidates)
        record_photo_request_missed(reason)
        logger.warning(
            "photo_request_missed request_id=%s reason=%s candidates=%s",
            get_request_id(),
            reason,
            len(photo_candidates),
        )


def _missed_photo_reason(
    photo_index: int | None,
    photo_candidates: list[PhotoCandidate],
) -> str:
    if photo_index is not None:
        return "index_out_of_range"
    if photo_candidates:
        return "no_marker"
    return "album_empty"
