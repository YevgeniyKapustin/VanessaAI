#!/usr/bin/env python
"""Regenerate knowledge vault folder index manifests (_index.yaml).

Usage:
    python scripts/reindex_knowledge.py                 # rebuild People only
    python scripts/reindex_knowledge.py People Lore/glossary Lore/events

The indexes are machine-manifests that the bot rebuilds after every write; this
script is a maintenance shortcut for manual edits (e.g. merging/renaming cards).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.knowledge.index import KnowledgeIndex
from app.knowledge.vault import KnowledgeVault


async def main() -> int:
    folders = sys.argv[1:] or ["People"]
    vault = KnowledgeVault()
    if not vault.is_configured:
        print("Knowledge vault is not configured (KNOWLEDGE_PATH empty)")
        return 1
    index = KnowledgeIndex(vault)
    for folder in folders:
        await index.rebuild_folder(folder)
        print(f"rebuilt {folder}/_index.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
