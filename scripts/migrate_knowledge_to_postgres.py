#!/usr/bin/env python
"""Import markdown knowledge vault files into Postgres knowledge_nodes.

Usage:
    python scripts/migrate_knowledge_to_postgres.py
    python scripts/migrate_knowledge_to_postgres.py --root knowledge

Reads the filesystem vault (KNOWLEDGE_PATH) and UPSERTs every note plus
folder indexes and sweep state. Then rebuilds _index.yaml documents in
Postgres.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from vanessa.config import settings
from vanessa.knowledge.format import ALL_FOLDERS, INDEX_FILENAME
from vanessa.knowledge.index import KnowledgeIndex
from vanessa.knowledge.store import (
    FilesystemKnowledgeStore,
    PostgresKnowledgeStore,
)
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.store.vault_lock import STATE_FILENAME

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def _import_notes(source: FilesystemKnowledgeStore, dest) -> int:
    imported = 0
    for folder in (*ALL_FOLDERS, "_archive"):
        notes = await source.list_notes(folder, recursive=True)
        for note in notes:
            await dest.write_note(note.relative_path, dict(note.meta), note.body)
            imported += 1
            print(f"upserted {note.relative_path}")
    return imported


def _yaml_paths() -> list[str]:
    yaml_paths = [STATE_FILENAME]
    for folder in ALL_FOLDERS:
        yaml_paths.append(f"{folder}/{INDEX_FILENAME}")
    yaml_paths.append(f"Culture/{INDEX_FILENAME}")
    yaml_paths.append(f"Logs/{INDEX_FILENAME}")
    return yaml_paths


async def _copy_yaml(source: FilesystemKnowledgeStore, dest) -> int:
    copied = 0
    for path in _yaml_paths():
        data = await source.read_yaml(path)
        if not data:
            continue
        await dest.write_yaml(path, data)
        copied += 1
        print(f"copied {path}")
    return copied


async def _rebuild_folder_indexes(dest) -> None:
    vault = KnowledgeVault(store=dest)
    index = KnowledgeIndex(vault)
    for folder in ("People", "Lore/glossary", "Lore/events", "Culture", "Logs", "inbox"):
        await index.rebuild_folder(folder)
        print(f"rebuilt index {folder}")


async def migrate(root: str) -> int:
    source = FilesystemKnowledgeStore(root)
    if not source.is_configured:
        print("Filesystem vault is not configured")
        return 1
    await source.ensure_structure()
    dest = PostgresKnowledgeStore()
    imported = await _import_notes(source, dest)
    copied = await _copy_yaml(source, dest)
    await _rebuild_folder_indexes(dest)
    print(f"done notes={imported} yaml={copied}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Migrate knowledge vault to Postgres")
    parser.add_argument("--root", default="", help="filesystem vault root")
    args = parser.parse_args()
    root = args.root.strip() or None
    return asyncio.run(migrate(root or settings.knowledge_path))


if __name__ == "__main__":
    raise SystemExit(main())
