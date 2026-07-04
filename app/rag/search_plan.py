from __future__ import annotations

from dataclasses import dataclass

from app.core.nicknames import find_nicknames_in_text
from app.llm.turn_planner import TurnPlan


@dataclass(frozen=True, slots=True)
class RagSearchPlan:
    semantic_queries: tuple[str, ...]
    fts_query: str


def build_main_rag_plan(message: str, turn_plan: TurnPlan) -> RagSearchPlan:
    original = message.strip()
    search = turn_plan.text.strip()

    semantic: list[str] = []
    if original:
        semantic.append(original)
    if search and search.lower() != original.lower():
        semantic.append(search)

    fts_parts: list[str] = []
    if search:
        fts_parts.append(search)
    elif original:
        fts_parts.append(original)
    fts_parts.extend(find_nicknames_in_text(original))

    fts_query = " ".join(dict.fromkeys(part for part in fts_parts if part))
    return RagSearchPlan(
        semantic_queries=tuple(semantic),
        fts_query=fts_query,
    )
