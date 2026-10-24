"""Guards and frontmatter for culture recommendation updates."""

from __future__ import annotations

from vanessa.knowledge.format import (
    TYPE_RECOMMENDATION,
    culture_kind_folder,
    slugify,
    today,
)
from vanessa.knowledge.memory.writer_fields import first_str, stripped_text
from vanessa.knowledge.memory.writer_guards import has_url


def recommendation_target(update: dict) -> tuple[str, str, str, str] | None:
    """Return ``(folder, kind, title, note_id)`` when the update can be written."""
    kind = stripped_text(update.get("kind"))
    folder = culture_kind_folder(kind)
    if folder is None:
        return None
    title = stripped_text(update.get("title"))
    # A movie/game/album has a name, not a link: a URL title is a menu,
    # a shop or a reminder payload that the planner misfiled.
    if not title or has_url(title):
        return None
    note_id = slugify(first_str(update.get("id"), title))
    return folder, kind, title, note_id


def recommendation_status(update: dict, existing: object) -> object:
    incoming = stripped_text(update.get("status"))
    if incoming:
        return incoming
    if existing:
        return existing.meta.get("status")
    return "proposed"


def recommendation_meta(
    update: dict,
    *,
    note_id: str,
    kind: str,
    title: str,
    status: object,
) -> dict:
    meta: dict = {
        "type": TYPE_RECOMMENDATION,
        "id": note_id,
        "kind": kind,
        "title": title,
        "status": status,
        "recommended_by": first_str(update.get("recommended_by")),
        "created": today(),
        "updated": today(),
    }
    rating = update.get("rating")
    if rating is not None:
        meta["rating"] = rating
    return meta
