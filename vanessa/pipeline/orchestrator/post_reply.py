import logging

from vanessa.contracts.messages import TaskKind
from vanessa.core.messages import context_message_to_payload
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.orchestrator.post_reply_jobs import _PostReplyJobsMixin

logger = logging.getLogger(
    "vanessa.pipeline.orchestrator.conversation_orchestrator"
)


class _PostReplyMixin(_PostReplyJobsMixin):
    async def _run_post_reply(self, ctx: TurnPipelineContext) -> None:
        """Run memory extraction + metrics + photo captioning.

        With a background executor injected, all are submitted as jobs and the
        reply returns immediately (non-blocking). Without one (unit tests /
        fallback) they run inline exactly as before.
        """
        caption_job = self._build_photo_caption_job(ctx)
        if self._dispatcher is not None:
            self._submit_worker_post_reply(ctx)
            self._submit_eval_if_needed(ctx)
            return
        if self._background is not None:
            self._submit_background_post_reply(ctx, caption_job)
            return
        await self._run_inline_post_reply(ctx, caption_job)

    def _submit_eval_if_needed(self, ctx: TurnPipelineContext) -> None:
        if self._eval is not None and self._eval.should_run() and self._background:
            self._background.submit(self._build_eval_job(ctx))

    def _submit_background_post_reply(
        self,
        ctx: TurnPipelineContext,
        caption_job,
    ) -> None:
        assert self._background is not None
        self._submit_memory_and_metrics(ctx)
        if self._eval is not None and self._eval.should_run():
            self._background.submit(self._build_eval_job(ctx))
        if caption_job is not None:
            self._background.submit(caption_job)

    def _submit_memory_and_metrics(self, ctx: TurnPipelineContext) -> None:
        assert self._background is not None
        if self._memory is not None:
            self._background.submit(self._build_memory_job(ctx))
        if self._metrics is not None:
            self._background.submit(self._build_metrics_job(ctx))

    async def _run_inline_post_reply(
        self, ctx: TurnPipelineContext, caption_job
    ) -> None:
        if caption_job is not None:
            await caption_job()
        await self._run_inline_memory(ctx)
        await self._run_inline_metrics(ctx)

    async def _run_inline_memory(self, ctx: TurnPipelineContext) -> None:
        if self._memory is None:
            return
        try:
            await self._memory.run(
                recent_messages=ctx.recent,
                source_message_ids=[ctx.user_msg.id] if ctx.user_msg else None,
                telegram_chat_id=ctx.turn.telegram_chat_id,
            )
        except Exception:
            logger.exception(
                "memory_stage_run_failed request_id=%s", get_request_id()
            )

    async def _run_inline_metrics(self, ctx: TurnPipelineContext) -> None:
        if self._metrics is None:
            return
        try:
            await self._metrics.run(
                self._messages,
                semantic=False,
                only_senders={ctx.turn.sender_telegram_id},
            )
        except Exception:
            logger.exception(
                "metrics_stage_run_failed request_id=%s", get_request_id()
            )

    def _submit_worker_post_reply(self, ctx: TurnPipelineContext) -> None:
        user_id = ctx.user_msg.id if ctx.user_msg is not None else 0
        chat_id = ctx.turn.telegram_chat_id
        assert self._dispatcher is not None
        self._dispatcher.submit(
            TaskKind.MEMORY_EXTRACT,
            {
                "telegram_chat_id": chat_id,
                "source_message_ids": [user_id] if user_id else [],
                "messages": [
                    context_message_to_payload(message) for message in ctx.recent
                ],
            },
            dedup_key=f"memory:{chat_id}:{user_id}",
        )
        self._dispatcher.submit(
            TaskKind.METRICS_SNAPSHOT,
            {"sender_telegram_id": ctx.turn.sender_telegram_id},
            dedup_key=f"metrics:{chat_id}:{user_id}",
        )
        if ctx.user_msg is not None and ctx.user_msg.attachments:
            first = ctx.user_msg.attachments[0]
            if isinstance(first, dict) and first.get("data_url"):
                self._dispatcher.submit(
                    TaskKind.PHOTO_CAPTION,
                    {"message_id": ctx.user_msg.id},
                    dedup_key=f"caption:{ctx.user_msg.id}",
                )
