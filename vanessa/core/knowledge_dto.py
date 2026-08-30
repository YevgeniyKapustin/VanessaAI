from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeBlock:
    """A vault fragment injected into the compose prompt (read path)."""

    path: str
    title: str
    kind: str
    content: str
    # Present when the block is one chunk of a People dossier (chunked detail
    # retrieval); None for whole-note blocks (portraits / lore / culture / logs).
    chunk_index: int | None = None
