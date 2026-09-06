from __future__ import annotations

from vanessa.core.messages import ContextBlock
from vanessa.core.protocols import ContextRetrieverProtocol
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.rag.search.search_plan import RagSearchPlan


async def search_with_plan(
    retriever: ContextRetrieverProtocol,
    query: str,
    rag_plan: RagSearchPlan,
    *,
    skip_fts: bool,
) -> list[ContextBlock]:
    return await retriever.search(
        query=query,
        skip_fts=skip_fts,
        semantic_queries=list(rag_plan.semantic_queries),
        fts_query=rag_plan.fts_query,
    )


async def retrieve_react_step(
    retriever: ContextRetrieverProtocol,
    query: str,
    rag_plan: RagSearchPlan,
    turn_plan: TurnPlan,
    *,
    step: int,
) -> list[ContextBlock]:
    step_plan = RagSearchPlan(
        semantic_queries=(query,),
        fts_query=rag_plan.fts_query if step == 0 else query,
    )
    return await search_with_plan(
        retriever,
        query,
        step_plan,
        skip_fts=turn_plan.skip_search and step > 0,
    )


def merge_react_blocks(
    blocks: list[ContextBlock],
    merged: list[ContextBlock],
    seen_anchors: set[int],
) -> list[ContextBlock]:
    new_blocks = [
        block for block in blocks if block.anchor_id not in seen_anchors
    ]
    for block in new_blocks:
        seen_anchors.add(block.anchor_id)
        merged.append(block)
    return new_blocks
