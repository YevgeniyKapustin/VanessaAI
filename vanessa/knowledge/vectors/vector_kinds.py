"""Vault-folder to retrieval-kind mapping for knowledge vectors."""

from __future__ import annotations

# Top-level vault folders that carry semantic content -> retrieval kind.
# The compaction archive holds the same semantically-summarized facts and quotes
# (with explanations) that were trimmed out of the live cards — embedding it
# keeps that history RAG-searchable, while the People alias index still ignores
# it (no person-card pollution).
SEMANTIC_FOLDERS: dict[str, str] = {
    "People": "people",
    "Lore": "lore",
    "Culture": "culture",
    "Logs": "logs",
    "_archive": "people",
}


def knowledge_kind_for_path(path: str) -> str | None:
    """Map a vault-relative note path to its semantic kind (people/lore/...)."""
    for folder, kind in SEMANTIC_FOLDERS.items():
        if path == folder or path.startswith(folder + "/"):
            return kind
    return None
