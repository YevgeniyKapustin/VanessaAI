"""Settings for pinned notes: vault notes Vanessa sees on every reply."""

from __future__ import annotations


class PinnedNotesMixin:
    """Agent settings for the pinned-notes retrieve step."""

    # Comma-separated vault paths, e.g. ``People/some-card.md``. Empty = off.
    # Set real paths only in the server ``.env.local``: notes are private.
    knowledge_pinned_notes: str = ""
    # Per-note cap on the text that goes into the compose prompt.
    knowledge_pinned_max_chars: int = 2500

    @property
    def pinned_note_paths(self) -> tuple[str, ...]:
        parts = (part.strip() for part in self.knowledge_pinned_notes.split(","))
        return tuple(part for part in parts if part)
