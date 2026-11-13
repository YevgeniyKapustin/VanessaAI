"""Announcement pieces: facts from code, bullets from the model.

Who, when, the links and the actor are facts — the app writes them itself,
so a reply quoting the message always carries them. The model only turns
the item list into 1–3 human bullets (or none).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, tzinfo

from services.worker.announce.content import WatchSpec
from services.worker.announce.models import Announcement

_TAG = "event"
_TAG_RE = re.compile(r"<\s*/?\s*" + _TAG + r"\s*>", re.IGNORECASE)
_EMPTY_LINK = re.compile(r"\[([^\[\]]+)\]\(\s*\)")
#: The model sees at most this many items; the newest are the useful ones.
MAX_ITEMS_IN_PROMPT = 40
#: Fallback shows this many raw titles.
FALLBACK_TITLES = 5
#: Lines that add nothing («остальное техническое…»).
_FILLER = re.compile(
    r"техническ|ничего не меняет|без изменений для продукт|остальн", re.IGNORECASE
)
#: Commits that are not a change for people: a merge, or the paperwork a
#: release carries (a spec, an ADR, a plan, a re-run of the MR checks). They
#: stay in ``Announcement.items`` — the card's разбор keeps every commit —
#: and only leave the pool the model picks its few bullets from.
_NOISE = re.compile(
    r"\b(?:merge|слить|свести)\b"
    r"|\b(?:adr|адр|спека|спеке|спеку|спецификаци\w*|документаци\w*)\b"
    r"|\bзафиксировать решени\w*"
    r"|запись о прогоне|проверки mr|в переносе",
    re.IGNORECASE,
)


def is_noise(title: str) -> bool:
    """A merge or a document: nothing changes for people because of it."""
    return bool(_NOISE.search(title or ""))



def local_when(announcement: Announcement, zone: tzinfo) -> str:
    """«12:54» in the chat's zone; empty string when the time is unknown."""
    if announcement.when is None:
        return ""
    moment = announcement.when
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(zone).strftime("%H:%M")


def item_lines(announcement: Announcement) -> list[str]:
    """The model's pool: real changes first, paperwork only if nothing is left."""
    titled = [item for item in announcement.items if item.title.strip()]
    changes = [item for item in titled if not is_noise(item.title)]
    return [
        f"- {item.title.strip()}" + (f" ({item.author})" if item.author else "")
        for item in (changes or titled)[:MAX_ITEMS_IN_PROMPT]
    ]


def _render(template: str, announcement: Announcement, *, zone: tzinfo, author: str,
            links: dict[str, str]) -> str:
    text = template.format(
        when=local_when(announcement, zone) or "—",
        url=announcement.url.strip(),
        started_by=author or announcement.actor_label,
        links=links,
        release=announcement.release.strip(),
    ).strip()
    # Nothing to point at → keep the words, drop the empty anchor.
    return _EMPTY_LINK.sub(r"\1", text) if "()" in text else text


def build_header(
    spec: WatchSpec, announcement: Announcement, *, zone: tzinfo, author: str = "",
    links: dict[str, str] | None = None,
) -> str:
    """``author`` overrides the source label (a resolved @-mention)."""
    return _render(spec.header, announcement, zone=zone, author=author, links=links or {})


def build_footer(
    spec: WatchSpec, announcement: Announcement, *, zone: tzinfo,
    links: dict[str, str] | None = None,
) -> str:
    """The link line; hidden while any configured link is missing."""
    if not spec.footer.strip() or not all((links or {}).values()):
        return ""
    return _render(spec.footer, announcement, zone=zone, author="", links=links or {})


def build_prompt(
    spec: WatchSpec, announcement: Announcement, *, stand_ready: bool | None, zone: tzinfo
) -> str:
    """The user prompt: a fenced data block, then the task."""
    lines = []
    if spec.context.strip():
        lines.append(spec.context.strip())
    lines += [
        f"время: {local_when(announcement, zone) or 'неизвестно'}",
        f"запустил: {announcement.actor_label}",
        f"ссылка: {announcement.url.strip() or 'нет ссылки'}",
        f"изменений в выпуске: {announcement.item_total}",
    ]
    if stand_ready is False:
        lines.append("стенд: пока не отвечает на запросы")
    items = item_lines(announcement)
    body = "\n".join(lines)
    if items:
        body += "\nизменения (от новых к старым):\n" + "\n".join(items)
    body = _TAG_RE.sub("", body)
    return f"<{_TAG}>\n{body}\n</{_TAG}>\n\n{spec.task.strip()}"


def clean_bullets(raw: str) -> list[str]:
    """Only real bullets survive: no headers, filler lines or links."""
    bullets: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text.startswith(("•", "-", "*")):
            continue
        text = re.sub(r"^[•\-*]+\s*", "", text).strip()
        if not text or _FILLER.search(text):
            continue
        bullets.append(f"• {text}")
    return bullets


def fallback_bullets(spec: WatchSpec, announcement: Announcement) -> list[str]:
    bullets = [
        spec.fallback_bullet.format(title=item.title.strip())
        for item in announcement.items[:FALLBACK_TITLES]
        if item.title.strip()
    ]
    hidden = announcement.item_total - len(bullets)
    if hidden > 0 and spec.fallback_more:
        bullets.append(spec.fallback_more.format(count=hidden))
    return bullets


def now_utc() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "FALLBACK_TITLES",
    "MAX_ITEMS_IN_PROMPT",
    "build_footer",
    "build_header",
    "build_prompt",
    "clean_bullets",
    "fallback_bullets",
    "is_noise",
    "item_lines",
    "local_when",
    "now_utc",
]
