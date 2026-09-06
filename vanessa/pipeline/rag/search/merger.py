from collections.abc import Mapping

from vanessa.config import settings
from vanessa.core.messages import StoredMessage


def merge_vector_search_hits(
    hit_lists: list[list[Mapping[str, object]]],
) -> list[Mapping[str, object]]:
    best: dict[int, Mapping[str, object]] = {}
    for hits in hit_lists:
        for hit in hits:
            message_id = int(hit["message_id"])
            score = float(hit["score"])
            current = best.get(message_id)
            if current is None or score > float(current["score"]):
                best[message_id] = hit
    return sorted(best.values(), key=lambda hit: float(hit["score"]), reverse=True)


def _reciprocal_rank_scores(
    vector_hits: list[Mapping[str, object]],
    fts_hits: list[StoredMessage],
) -> dict[int, float]:
    scored: dict[int, float] = {}
    for rank, hit in enumerate(vector_hits):
        mid = int(hit["message_id"])
        scored[mid] = scored.get(mid, 0.0) + (1.0 / (rank + 1))
    for rank, message in enumerate(fts_hits):
        scored[message.id] = scored.get(message.id, 0.0) + (1.0 / (rank + 1))
    return scored


def _take_context_ids(
    sorted_ids: list[int],
    context_min: int,
    context_max: int,
) -> list[int]:
    if not sorted_ids:
        return []
    if len(sorted_ids) < context_min:
        return sorted_ids
    return sorted_ids[: min(len(sorted_ids), context_max)]


def merge_hybrid_results(
    vector_hits: list[Mapping[str, object]],
    fts_hits: list[StoredMessage],
    context_min: int = settings.rag_context_min,
    context_max: int = settings.rag_context_max,
) -> list[int]:
    scored = _reciprocal_rank_scores(vector_hits, fts_hits)
    sorted_ids = sorted(scored, key=scored.get, reverse=True)
    return _take_context_ids(sorted_ids, context_min, context_max)
