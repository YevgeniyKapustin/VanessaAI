import logging
import time

from vanessa.core.protocols import ContextRetrieverProtocol, UnitOfWorkProtocol
from vanessa.core.request_context import get_request_id
from vanessa.infrastructure.websearch.protocols import WebSearchService
from vanessa.knowledge.retriever import KnowledgeRetriever
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.humor_pipeline import HumorPipelineProtocol
from vanessa.pipeline.llm.memes import MemeCatalog, MemeDecider
from vanessa.pipeline.rag.search.react_retriever import retrieve_with_react
from vanessa.pipeline.stages.query import _semantic_query
from vanessa.pipeline.stages.retrieve_extras import _RetrieveExtrasMixin
from vanessa.pipeline.stages.retrieve_knowledge import _RetrieveKnowledgeMixin

logger = logging.getLogger("vanessa.pipeline.stages")


class RetrieveStage(_RetrieveKnowledgeMixin, _RetrieveExtrasMixin):
    def __init__(
        self,
        retriever: ContextRetrieverProtocol,
        humor_pipeline: HumorPipelineProtocol,
        uow: UnitOfWorkProtocol | None,
        *,
        knowledge: KnowledgeRetriever | None = None,
        meme_catalog: MemeCatalog | None = None,
        meme_decider: MemeDecider | None = None,
        web_search: WebSearchService | None = None,
    ) -> None:
        self._retriever = retriever
        self._humor = humor_pipeline
        self._uow = uow
        self._knowledge = knowledge
        self._meme_catalog = meme_catalog
        self._meme_decider = meme_decider
        # Live web search (the "googling" skill); None disables it (default).
        self._web_search = web_search

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if self._uow is not None:
            await self._uow.commit()

        assert ctx.turn_plan is not None
        self._mark_embed_ms(ctx)

        # Semantic archive (People/Lore/Culture/Logs) is the primary RAG source —
        # those notes are already semantic summaries, unlike raw message history.
        semantic_query = _semantic_query(ctx.turn_plan, ctx.turn.message)
        people_files = await self._resolve_people_files(ctx)
        knowledge_indexes = self._knowledge_indexes(ctx, people_files)

        semantic_started = time.perf_counter()
        semantic_found = await self._fetch_knowledge(
            ctx, semantic_query, knowledge_indexes, people_files
        )
        ctx.semantic_ms = (time.perf_counter() - semantic_started) * 1000

        rag_started = time.perf_counter()
        # Raw-message history is only a fallback: run it when the archive had
        # nothing relevant, or as an extra pass for deep multi-step searches.
        if not semantic_found or ctx.turn_plan.deep_search:
            ctx.context_blocks = await retrieve_with_react(
                self._retriever,
                ctx.turn.message,
                ctx.turn_plan,
            )
        ctx.rag_ms = (time.perf_counter() - rag_started) * 1000

        # Live web search (the "googling" skill): runs alongside RAG when the
        # planner flagged the turn. Fail-open — results only ever enrich the
        # compose prompt, never block the reply.
        await self._run_web_search(ctx)

        humor_started = time.perf_counter()
        ctx.humor_quotes = await self._humor.fetch_quotes(
            ctx.turn_plan,
            ctx.turn.message,
        )
        ctx.humor_rag_ms = (time.perf_counter() - humor_started) * 1000

        if ctx.humor_quotes:
            logger.info(
                "turn_stage humor_rag request_id=%s humor_query=%r quotes=%s "
                "humor_rag_ms=%.1f",
                get_request_id(),
                ctx.turn_plan.humor_query,
                len(ctx.humor_quotes),
                ctx.humor_rag_ms,
            )

        self._maybe_attach_memes(ctx)

        logger.info(
            "turn_stage rag request_id=%s context=%s semantic_found=%s "
            "deep_search=%s knowledge=%s meme_blocks=%s meme_menu=%s "
            "semantic_ms=%.1f rag_ms=%.1f",
            get_request_id(),
            ctx.context_count,
            semantic_found,
            ctx.turn_plan.deep_search,
            len(ctx.knowledge_blocks),
            len(ctx.meme_blocks),
            len(ctx.meme_menu),
            ctx.semantic_ms,
            ctx.rag_ms,
        )
        return True
