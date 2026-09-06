"""Path helpers for the filesystem knowledge vault."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from vanessa.knowledge.format import INDEX_FILENAME, parse_frontmatter
from vanessa.knowledge.schema import VaultNote


def resolve_vault_path(root: Path, relative_path: str) -> Path:
    parts = PurePosixPath(relative_path).parts
    path = root.joinpath(*parts).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError("path escapes vault root")
    return path


def list_markdown_notes(
    root: Path,
    folder: str,
    *,
    recursive: bool = False,
) -> list[VaultNote]:
    folder_path = resolve_vault_path(root, folder) if folder else root
    if not folder_path.is_dir():
        return []
    pattern = "**/*.md" if recursive else "*.md"
    notes: list[VaultNote] = []
    for md in sorted(folder_path.glob(pattern)):
        if md.name == INDEX_FILENAME:
            continue
        rel = md.relative_to(root).as_posix()
        meta, body = parse_frontmatter(md.read_text(encoding="utf-8"))
        notes.append(
            VaultNote(
                relative_path=rel,
                meta=meta,
                body=body,
                updated_at=md.stat().st_mtime,
            )
        )
    return notes
