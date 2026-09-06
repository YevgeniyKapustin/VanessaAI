from __future__ import annotations

from dataclasses import dataclass

from vanessa.knowledge.users.nicknames import find_nicknames_in_text
from vanessa.pipeline.decision.turn_plan import TurnPlan


@dataclass(frozen=True, slots=True)
class RagSearchPlan:
    semantic_queries: tuple[str, ...]
    fts_query: str


def _semantic_queries(original: str, search: str) -> list[str]:
    semantic: list[str] = []
    if original:
        semantic.append(original)
    if search and search.lower() != original.lower():
        semantic.append(search)
    return semantic


def _fts_parts(original: str, search: str) -> list[str]:
    fts_parts: list[str] = []
    if search:
        fts_parts.append(search)
    elif original:
        fts_parts.append(original)
    fts_parts.extend(find_nicknames_in_text(original))
    return fts_parts


def build_main_rag_plan(message: str, turn_plan: TurnPlan) -> RagSearchPlan:
    original = message.strip()
    search = turn_plan.text.strip()
    fts_parts = _fts_parts(original, search)
    fts_query = " ".join(dict.fromkeys(part for part in fts_parts if part))
    return RagSearchPlan(
        semantic_queries=tuple(_semantic_queries(original, search)),
        fts_query=fts_query,
    )
