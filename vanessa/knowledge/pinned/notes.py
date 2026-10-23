"""PinnedNotes: vault notes Vanessa sees on every reply.

Some knowledge is hers to keep in mind all the time, not only when the
sender's own card has it (for example the owner's team at work). The paths
come from settings, so private notes stay in the server env, not the repo.
A note that is missing or fails to read is skipped: the turn goes on.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import PurePosixPath

from vanessa.core.knowledge_dto import KnowledgeBlock
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.vault import KnowledgeVault

logger = logging.getLogger(__name__)

PINNED_KIND = "note"


def _is_heading(line: str) -> bool:
    return line.startswith("#")


def pinned_text(body: str, max_chars: int) -> str:
    """Note body without blank lines and empty sections, clipped."""
    lines = [line.rstrip() for line in (body or "").splitlines() if line.strip()]
    kept: list[str] = []
    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if _is_heading(line) and (not following or _is_heading(following)):
            continue
        kept.append(line)
    text = "\n  ".join(kept)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def pinned_title(note: VaultNote) -> str:
    meta = note.meta or {}
    for key in ("nickname", "title"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return PurePosixPath(note.relative_path).stem


class PinnedNotes:
    """Reads the configured notes into compose knowledge blocks."""

    def __init__(
        self,
        vault: KnowledgeVault,
        paths: Sequence[str],
        *,
        max_chars: int,
    ) -> None:
        self._vault = vault
        self._paths = tuple(paths)
        self._max_chars = max_chars

    async def blocks(self) -> list[KnowledgeBlock]:
        blocks: list[KnowledgeBlock] = []
        for path in self._paths:
            block = await self._read_block(path)
            if block is not None:
                blocks.append(block)
        return blocks

    async def _read_block(self, path: str) -> KnowledgeBlock | None:
        try:
            note = await self._vault.read_note(path)
        except Exception:
            logger.exception("pinned_note_read_failed path=%s", path)
            return None
        if note is None:
            logger.warning("pinned_note_missing path=%s", path)
            return None
        content = pinned_text(note.body, self._max_chars)
        if not content:
            return None
        return KnowledgeBlock(
            path=path,
            title=pinned_title(note),
            kind=PINNED_KIND,
            content=content,
        )
