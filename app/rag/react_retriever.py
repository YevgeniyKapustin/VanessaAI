from __future__ import annotations

import logging
import re

from app.config import settings
from app.core.messages import ContextBlock
from app.core.protocols import ContextRetrieverProtocol
from app.llm.turn_planner import TurnPlan
from app.rag.search_plan import RagSearchPlan, build_main_rag_plan

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-zа-яё]{4,}", re.IGNORECASE)
_STOP = frozenset(
    {"ванесса", "vanessa", "подскажи", "расскажи", "объясни", "помоги", "найди"}
)


def derive_follow_up_query(
    message: str,
    blocks: list[ContextBlock],
    prior_queries: list[str],
) -> str | None:
    if len(blocks) >= settings.rag_react_min_blocks:
        return None

    seen = {query.strip().lower() for query in prior_queries if query.strip()}
    tokens = [
        token
        for token in _TOKEN.findall(message.lower())
        if token not in _STOP
    ]
    for token in tokens:
        if token not in seen:
            return token
    return None


async def retrieve_with_react(
    retriever: ContextRetrieverProtocol,
    message: str,
    turn_plan: TurnPlan,
    *,
    max_steps: int | None = None,
) -> list[ContextBlock]:
    steps = max_steps or settings.rag_react_max_steps
    if steps <= 1 or not turn_plan.deep_search:
        rag_plan = build_main_rag_plan(message, turn_plan)
        return await retriever.search(
            query=turn_plan.text or message,
            skip_fts=turn_plan.skip_search,
            semantic_queries=list(rag_plan.semantic_queries),
            fts_query=rag_plan.fts_query,
        )

    rag_plan = build_main_rag_plan(message, turn_plan)
    queries = list(rag_plan.semantic_queries) or [turn_plan.text or message]
    merged: list[ContextBlock] = []
    seen_anchors: set[int] = set()
    prior_queries: list[str] = []

    for step in range(steps):
        query = queries[min(step, len(queries) - 1)]
        prior_queries.append(query)
        plan = RagSearchPlan(
            semantic_queries=(query,),
            fts_query=rag_plan.fts_query if step == 0 else query,
        )
        blocks = await retriever.search(
            query=query,
            skip_fts=turn_plan.skip_search and step > 0,
            semantic_queries=list(plan.semantic_queries),
            fts_query=plan.fts_query,
        )
        new_blocks = [
            block for block in blocks if block.anchor_id not in seen_anchors
        ]
        for block in new_blocks:
            seen_anchors.add(block.anchor_id)
            merged.append(block)

        logger.info(
            "react_search step=%s query=%r new_blocks=%s total=%s",
            step + 1,
            query,
            len(new_blocks),
            len(merged),
        )

        if len(merged) >= settings.rag_react_min_blocks:
            break
        follow_up = derive_follow_up_query(message, merged, prior_queries)
        if not follow_up:
            break
        queries.append(follow_up)

    return merged
