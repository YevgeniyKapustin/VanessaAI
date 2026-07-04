from collections.abc import Mapping

from app.config import settings
from app.core.messages import StoredMessage


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


def merge_hybrid_results(
    vector_hits: list[Mapping[str, object]],
    fts_hits: list[StoredMessage],
    context_min: int = settings.rag_context_min,
    context_max: int = settings.rag_context_max,
) -> list[int]:
    scored: dict[int, float] = {}

    for rank, hit in enumerate(vector_hits):
        mid = int(hit["message_id"])
        scored[mid] = scored.get(mid, 0.0) + (1.0 / (rank + 1))

    for rank, message in enumerate(fts_hits):
        scored[message.id] = scored.get(message.id, 0.0) + (1.0 / (rank + 1))

    sorted_ids = sorted(scored, key=scored.get, reverse=True)
    if not sorted_ids:
        return []

    target = min(len(sorted_ids), context_max)
    if len(sorted_ids) >= context_min:
        target = min(len(sorted_ids), context_max)
    else:
        target = len(sorted_ids)

    return sorted_ids[:target]
