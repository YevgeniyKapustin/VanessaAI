import logging

from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.db.repository import MessageRepository
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger(
    "vanessa.pipeline.orchestrator.conversation_orchestrator"
)


class _PostReplyJobsMixin:
    def _build_memory_job(self, ctx: TurnPipelineContext):
        recent = ctx.recent
        source_ids = [ctx.user_msg.id] if ctx.user_msg is not None else None
        chat_id = ctx.turn.telegram_chat_id

        async def job() -> None:
            try:
                assert self._memory is not None
                await self._memory.run(
                    recent_messages=recent,
                    source_message_ids=source_ids,
                    telegram_chat_id=chat_id,
                )
            except Exception:
                logger.exception(
                    "memory_stage_run_failed request_id=%s", get_request_id()
                )

        return job

    def _build_metrics_job(self, ctx: TurnPipelineContext):
        sender_id = ctx.turn.sender_telegram_id
        if sender_id is None or self._metrics is None:
            return None
        return self._sender_metrics_job(sender_id)

    def _sender_metrics_job(self, sender_id: int):
        async def job() -> None:
            try:
                await self._run_sender_metrics(sender_id)
            except Exception:
                logger.exception(
                    "metrics_stage_run_failed request_id=%s", get_request_id()
                )

        return job

    async def _run_sender_metrics(self, sender_id: int) -> None:
        assert self._metrics is not None
        if self._session_factory is not None:
            # The request-scoped repo dies with the response, so metrics
            # must open its own session in the background.
            async with self._session_factory() as session:
                await self._metrics.run(
                    MessageRepository(session),
                    semantic=False,
                    only_senders={sender_id},
                )
            return
        await self._metrics.run(
            self._messages,
            semantic=False,
            only_senders={sender_id},
        )

    def _build_eval_job(self, ctx: TurnPipelineContext):
        question = ctx.turn.message
        answer = ctx.reply or ""
        context = self._eval_context_text(ctx)

        async def job() -> None:
            try:
                assert self._eval is not None
                await self._eval.evaluate(
                    question=question,
                    answer=answer,
                    context=context,
                )
            except Exception:
                logger.exception(
                    "rag_eval_failed request_id=%s", get_request_id()
                )

        return job

    def _build_photo_caption_job(self, ctx: TurnPipelineContext):
        """Enrich a photo message with a short generated caption (background).

        The caption is stored in ``messages.photo_caption`` and folded into the
        FTS search_vector, so a bare photo becomes findable "by meaning" in RAG
        and is listed (with its caption) in the photo album the compose model
        can pick from. Returns None when there is nothing to caption.
        """
        parsed = self._photo_caption_target(ctx)
        if parsed is None:
            return None
        attachment, message_id = parsed

        async def job() -> None:
            await self._run_photo_caption_job(attachment, message_id)

        return job

    async def _run_photo_caption_job(
        self, attachment: ImageAttachment, message_id: int
    ) -> None:
        try:
            caption = await self._photo_captioner.generate(attachment)
            if not caption:
                return
            await self._persist_photo_caption(message_id, caption)
            logger.info(
                "photo_caption_stored message_id=%s caption=%r",
                message_id,
                caption,
            )
        except Exception:
            logger.exception(
                "photo_caption_stage_failed request_id=%s", get_request_id()
            )

    async def _persist_photo_caption(self, message_id: int, caption: str) -> None:
        if self._session_factory is not None:
            # The request-scoped repo dies with the response, so the job
            # opens its own session in the background.
            async with self._session_factory() as session:
                await MessageRepository(session).update_photo_caption(
                    message_id, caption
                )
            return
        await self._messages.update_photo_caption(message_id, caption)

    def _photo_caption_target(
        self,
        ctx: TurnPipelineContext,
    ) -> tuple[ImageAttachment, int] | None:
        if self._photo_captioner is None or not settings.vision_photo_caption_enabled:
            return None
        user_msg = ctx.user_msg
        if user_msg is None or not user_msg.attachments:
            return None
        return _caption_attachment_from_user(user_msg)

    @staticmethod
    def _eval_context_text(ctx: TurnPipelineContext) -> str:
        """Flatten the retrieved context into plain text for the judge."""
        parts = _stripped_knowledge(ctx)
        parts.extend(_stripped_context_messages(ctx))
        parts.extend(quote.strip() for quote in ctx.humor_quotes if quote.strip())
        return "\n\n".join(parts)


def _caption_attachment_from_user(
    user_msg,
) -> tuple[ImageAttachment, int] | None:
    first_attachment = user_msg.attachments[0]
    if not isinstance(first_attachment, dict):
        return None
    attachment = ImageAttachment.from_dict(first_attachment)
    if not attachment.data_url:
        return None
    return attachment, user_msg.id


def _stripped_knowledge(ctx: TurnPipelineContext) -> list[str]:
    parts: list[str] = []
    for block in ctx.knowledge_blocks:
        if block.content.strip():
            parts.append(block.content.strip())
    return parts


def _stripped_context_messages(ctx: TurnPipelineContext) -> list[str]:
    parts: list[str] = []
    for block in ctx.context_blocks:
        for message in block.messages:
            if message.content.strip():
                parts.append(message.content.strip())
    return parts
