"""Filesystem iteration over People vault cards."""

from __future__ import annotations

from pathlib import Path

from vanessa.config.settings import settings
from vanessa.knowledge.format import parse_frontmatter
from vanessa.knowledge.schema import VaultNote


def people_dir() -> Path | None:
    """Path to the vault People folder, or None when the vault is unconfigured."""
    raw = settings.knowledge_path.strip() if settings.knowledge_path else ""
    if not raw:
        return None
    root = Path(raw).resolve()
    people = root / "People"
    return people if people.is_dir() else None


def _note_from_md(md: Path) -> VaultNote | None:
    try:
        meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(meta, dict):
        return None
    return VaultNote(
        relative_path=md.as_posix(),
        meta=meta,
        body=body,
        updated_at=md.stat().st_mtime,
    )


def iter_people_notes_fs():
    people = people_dir()
    if people is None:
        return []
    notes = []
    for md in sorted(people.glob("*.md")):
        note = _note_from_md(md)
        if note is None:
            continue
        notes.append(note)
    return notes


def _md_stat_entry(md: Path) -> tuple | None:
    if md.name == "_index.yaml":
        return None
    try:
        stat = md.stat()
    except OSError:
        return None
    return (md.as_posix(), stat.st_mtime, stat.st_size)


def people_signature_fs() -> tuple:
    people = people_dir()
    if people is None:
        return ()
    signature: list = []
    for md in sorted(people.glob("*.md")):
        entry = _md_stat_entry(md)
        if entry is None:
            continue
        signature.append(entry)
    return tuple(signature)
