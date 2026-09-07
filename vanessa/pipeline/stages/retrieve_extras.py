import logging
import time

from vanessa.config.settings import settings
from vanessa.core.request_context import get_request_id
from vanessa.core.session.channel_keys import dialogue_session_key, turn_channel
from vanessa.infrastructure.observability.metrics import record_web_search
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger("vanessa.pipeline.stages")


class _RetrieveExtrasMixin:
    def _maybe_attach_memes(self, ctx: TurnPipelineContext) -> None:
        # Curated memes (hybrid): when the planner allows humor, a keyword match
        # offers that specific meme; otherwise (if enabled) a compact menu is
        # offered so the bot can pick a meme itself. Both paths pass the same
        # anti-spam gate (probability + per-chat cooldown).
        catalog = self._meme_catalog
        decider = self._meme_decider
        plan = ctx.turn_plan
        if plan is None or not plan.humor_ok or catalog is None:
            return
        if decider is None or not catalog.enabled:
            return
        self._offer_memes(ctx, catalog, decider)

    def _offer_memes(self, ctx: TurnPipelineContext, catalog, decider) -> None:
        chat_id = dialogue_session_key(
            channel=turn_channel(ctx.turn),
            telegram_chat_id=ctx.turn.telegram_chat_id,
        )
        matched = catalog.match(ctx.turn.message)
        if matched:
            self._assign_matched_memes(ctx, chat_id, matched, decider)
            return
        self._assign_meme_menu(ctx, chat_id, catalog, decider)

    def _assign_matched_memes(self, ctx, chat_id, matched, decider) -> None:
        if not decider.decide(chat_id):
            return
        ctx.meme_blocks = matched
        decider.register_meme(chat_id)

    def _assign_meme_menu(self, ctx, chat_id, catalog, decider) -> None:
        if not catalog.offer_on_humor:
            return
        if not decider.decide(chat_id):
            return
        ctx.meme_menu = catalog.offerable()
        decider.register_meme(chat_id)

    async def _run_web_search(self, ctx: TurnPipelineContext) -> None:
        """Run the live web search when the planner flagged the turn.

        Fail-open by design: a search error or an empty result never blocks the
        turn — the composer simply answers from the archive / its own knowledge.
        Timing and outcome are recorded so search quality is observable.
        """
        assert ctx.turn_plan is not None
        if not settings.web_search_enabled or self._web_search is None:
            return
        query = (ctx.turn_plan.web_query or "").strip()
        if not ctx.turn_plan.web_search or not query:
            return
        started = time.perf_counter()
        try:
            results = await self._web_search.search(
                query,
                limit=settings.web_search_max_results,
            )
            ctx.web_blocks = list(results)
            status = "found" if results else "empty"
        except Exception:
            # Fail-open: never let a broken search API block the reply.
            logger.exception(
                "web_search_failed request_id=%s query=%r",
                get_request_id(),
                query,
            )
            ctx.web_blocks = []
            status = "error"
        ctx.web_ms = (time.perf_counter() - started) * 1000
        record_web_search(status, ctx.web_ms)
        logger.info(
            "turn_stage web_search request_id=%s query=%r results=%s web_ms=%.1f",
            get_request_id(),
            query,
            len(ctx.web_blocks),
            ctx.web_ms,
        )
