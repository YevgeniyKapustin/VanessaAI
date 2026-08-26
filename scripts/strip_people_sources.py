"""Strip ``source_message_ids`` from the frontmatter of People/*.md notes.

People cards must not carry a growing list of source message IDs, so this
removes the existing accumulated blocks. Text-based edit to preserve the
original frontmatter formatting of the remaining keys.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - Python < 3.7
    pass

PEOPLE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "People"

_KEY_RE = re.compile(r"^(\s*)source_message_ids:\s*$")


def strip_source_block(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    removed = 0
    while i < len(lines):
        match = _KEY_RE.match(lines[i])
        if match:
            # Skip the key line and any following "- item" lines.
            i += 1
            while i < len(lines) and re.match(r"^\s*-(\s|$)", lines[i]):
                i += 1
            removed += 1
            continue
        out.append(lines[i])
        i += 1
    return out, removed


def main() -> None:
    total_files = 0
    total_blocks = 0
    for path in sorted(PEOPLE_DIR.glob("*.md")):
        original = path.read_text(encoding="utf-8").splitlines(keepends=True)
        cleaned, removed = strip_source_block(original)
        if removed:
            path.write_text("".join(cleaned), encoding="utf-8")
            total_files += 1
            total_blocks += removed
            print(f"cleaned: {path.name} ({removed} block(s))")
    print(f"\nDone: {total_files} file(s), {total_blocks} block(s) removed")


if __name__ == "__main__":
    main()
