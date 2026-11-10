"""One fact worth telling the chat about, whatever produced it.

A *watch* turns an external fact (a successful deploy, a finished rollout, a
published release) into an ``Announcement``; the announcer only knows this
shape. A new kind of notification is therefore an adapter plus a YAML, not
a copy of the polling loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Actor:
    """Who caused the event, as the source reports them."""

    name: str = ""
    username: str = ""

    def label(self) -> str:
        name = self.name.strip()
        handle = f"@{self.username}" if self.username else ""
        if name and handle:
            return f"{name} ({handle})"
        return name or handle or "неизвестно"


@dataclass(frozen=True, slots=True)
class Item:
    """One change in the release; ``title`` goes to the model as-is."""

    title: str
    author: str = ""


@dataclass(frozen=True, slots=True)
class Announcement:
    """A new event: ``key`` grows over time and is what dedupe compares."""

    key: int
    when: datetime | None = None
    url: str = ""
    actor: Actor | None = None
    items: tuple[Item, ...] = ()
    total: int = 0
    #: Release label for the header («v0.1.7», «v0.1.6 (79545)»), if any.
    release: str = ""

    @property
    def actor_label(self) -> str:
        return (self.actor or Actor()).label()

    @property
    def item_total(self) -> int:
        return max(self.total, len(self.items))


__all__ = ["Actor", "Announcement", "Item"]
