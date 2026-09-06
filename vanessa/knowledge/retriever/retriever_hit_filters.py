"""Score / kind / path predicates for vector and FTS hits."""

from __future__ import annotations

from vanessa.knowledge.vectors.vector_index import knowledge_kind_for_path

# Compaction archive area (top-level, excluded from the People alias index but
# embedded for RAG). Its notes are chunked like dossiers, so a retrieved
# archive hit must be rendered as the matching chunk, never the whole file.
_ARCHIVE_PREFIX = "_archive/"


def score_too_low(hit: dict, min_score: float) -> bool:
    return float(hit["score"]) < min_score


def kind_excluded(hit: dict, indexes: set[str]) -> bool:
    return bool(indexes) and hit["kind"] not in indexes


def self_path_suppressed(
    path: str,
    *,
    self_paths: set[str],
    has_non_self_target: bool,
) -> bool:
    return has_non_self_target and path in self_paths


def skip_vector_hit(
    hit: dict,
    *,
    min_score: float,
    indexes: set[str],
    self_paths: set[str],
    has_non_self_target: bool,
) -> bool:
    if score_too_low(hit, min_score):
        return True
    if kind_excluded(hit, indexes):
        return True
    return self_path_suppressed(
        hit["path"],
        self_paths=self_paths,
        has_non_self_target=has_non_self_target,
    )


def is_people_chunk_hit(hit: dict, *, chunked_detail: bool) -> bool:
    chunk_index = hit.get("chunk_index")
    return (
        hit["kind"] == "people"
        and chunk_index is not None
        and (chunked_detail or hit["path"].startswith(_ARCHIVE_PREFIX))
    )


def fts_kind_excluded(relative_path: str, indexes: set[str]) -> bool:
    if not indexes:
        return False
    kind = knowledge_kind_for_path(relative_path)
    return kind is None or kind not in indexes
