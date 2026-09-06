import logging
import time

from vanessa.knowledge.people.entities import is_person_focused
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.rag.search.search_plan import build_main_rag_plan

logger = logging.getLogger("vanessa.pipeline.stages")


class _RetrieveKnowledgeMixin:
    def _mark_embed_ms(self, ctx: TurnPipelineContext) -> None:
        assert ctx.turn_plan is not None
        if not ctx.turn_plan.skip_search and build_main_rag_plan(
            ctx.turn.message,
            ctx.turn_plan,
        ).semantic_queries:
            embed_started = time.perf_counter()
            ctx.embed_ms = (time.perf_counter() - embed_started) * 1000

    async def _resolve_people_files(self, ctx: TurnPipelineContext) -> list[str]:
        # Deterministic participant resolution: which People dossiers are
        # relevant to this turn (mentioned in the message + recent window).
        # This powers multi-person retrieval — all mentioned people get pulled,
        # not a single arbitrary match.
        if self._knowledge is None:
            return []
        try:
            return await self._knowledge.resolve_people(
                ctx.turn.message,
                ctx.recent,
                sender_name=ctx.sender_name,
            )
        except Exception:
            logger.exception("people_resolve_failed, ignoring")
            return []

    def _knowledge_indexes(
        self,
        ctx: TurnPipelineContext,
        people_files: list[str],
    ) -> list[str]:
        assert ctx.turn_plan is not None
        knowledge_indexes = list(ctx.turn_plan.knowledge_indexes)
        # Deterministic fallback: if the message is clearly about people and the
        # planner (LLM) omitted the "people" index, force it — the resolver is
        # cheap and exact, the planner is not.
        if (
            people_files
            and "people" not in knowledge_indexes
            and is_person_focused(ctx.turn.message)
        ):
            knowledge_indexes.append("people")
            logger.info(
                "people_index_forced_by_resolver files=%s",
                sorted(people_files),
            )
        return knowledge_indexes

    async def _fetch_knowledge(
        self,
        ctx: TurnPipelineContext,
        semantic_query: str,
        knowledge_indexes: list[str],
        people_files: list[str],
    ) -> bool:
        if self._knowledge is None:
            return False
        assert ctx.turn_plan is not None
        try:
            ctx.knowledge_blocks = await self._knowledge.fetch_semantic(
                semantic_query,
                knowledge_indexes=tuple(knowledge_indexes),
                knowledge_query=ctx.turn_plan.knowledge_query,
                humor_ok=ctx.turn_plan.humor_ok,
                humor_query=ctx.turn_plan.humor_query,
                user_message=ctx.turn.message,
                people_detail=ctx.turn_plan.knowledge_detail,
                people_files=people_files or None,
            )
        except Exception:
            # Fail-open: a semantic-search failure (e.g. Qdrant down) must
            # never block the turn — fall back to raw-message RAG.
            logger.exception(
                "semantic_search_failed query=%r, using raw RAG fallback",
                semantic_query,
            )
            ctx.knowledge_blocks = []
        return bool(ctx.knowledge_blocks)
