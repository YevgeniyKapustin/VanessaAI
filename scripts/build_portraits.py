#!/usr/bin/env python
"""Regenerate the compact LLM portraits for every People dossier.

Usage:
    python scripts/build_portraits.py [--force]

Compresses each People card into a 3-5 sentence portrait stored in the card's
frontmatter. Without ``--force`` only stale cards are rebuilt (no portrait yet,
or the dossier changed since the last run). Run after bulk manual edits to the
vault, or to seed portraits for the first time.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from vanessa.config.settings import settings
from vanessa.knowledge.portraits import PortraitBuilder
from vanessa.knowledge.vault import KnowledgeVault


async def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact person portraits")
    parser.add_argument("--force", action="store_true", help="rebuild every portrait")
    args = parser.parse_args()

    vault = KnowledgeVault()
    if not vault.is_configured:
        print("Knowledge vault is not configured (KNOWLEDGE_PATH empty)")
        return 1

    builder = PortraitBuilder(
        vault,
        max_chars=settings.knowledge_portrait_max_chars,
    )
    updated = await builder.run(force=args.force)
    print(f"portraits rebuilt: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
