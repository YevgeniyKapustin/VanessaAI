from __future__ import annotations

import logging
import re

from vanessa.config import settings
from vanessa.core.messages import ContextBlock
from vanessa.core.protocols import ContextRetrieverProtocol
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.rag.search.react_steps import (
    merge_react_blocks,
    retrieve_react_step,
    search_with_plan,
)
from vanessa.pipeline.rag.search.search_plan import build_main_rag_plan

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z\u0430-\u044f\u0451]{4,}", re.IGNORECASE)
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


def _follow_up_or_stop(
    message: str,
    merged: list[ContextBlock],
    prior_queries: list[str],
) -> str | None:
    if len(merged) >= settings.rag_react_min_blocks:
        return None
    return derive_follow_up_query(message, merged, prior_queries)


async def retrieve_with_react(
    retriever: ContextRetrieverProtocol,
    message: str,
    turn_plan: TurnPlan,
    *,
    max_steps: int | None = None,
) -> list[ContextBlock]:
    steps = max_steps or settings.rag_react_max_steps
    rag_plan = build_main_rag_plan(message, turn_plan)
    if steps <= 1 or not turn_plan.deep_search:
        return await search_with_plan(
            retriever,
            turn_plan.text or message,
            rag_plan,
            skip_fts=turn_plan.skip_search,
        )

    queries = list(rag_plan.semantic_queries) or [turn_plan.text or message]
    merged: list[ContextBlock] = []
    seen_anchors: set[int] = set()
    prior_queries: list[str] = []

    for step in range(steps):
        query = queries[min(step, len(queries) - 1)]
        prior_queries.append(query)
        blocks = await retrieve_react_step(
            retriever,
            query,
            rag_plan,
            turn_plan,
            step=step,
        )
        new_blocks = merge_react_blocks(blocks, merged, seen_anchors)
        logger.info(
            "react_search step=%s query=%r new_blocks=%s total=%s",
            step + 1,
            query,
            len(new_blocks),
            len(merged),
        )
        follow_up = _follow_up_or_stop(message, merged, prior_queries)
        if not follow_up:
            break
        queries.append(follow_up)

    return merged
