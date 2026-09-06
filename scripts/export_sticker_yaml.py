"""Rewrite sticker ``index`` / ``file_id`` in stickers.yaml, preserving the rest."""

from __future__ import annotations


def _parse_name(stripped: str) -> str:
    value = stripped.split(":", 1)[1].strip()
    return value.strip("\"'").strip()


def _yaml_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _insert_file_id_after(out: list[str], file_id: str, prefix: str) -> bool:
    for pos, line in enumerate(out):
        if line.strip().startswith(prefix):
            indent = _yaml_indent(line)
            out.insert(pos + 1, f'{indent}file_id: "{file_id}"\n')
            return True
    return False


def _rewrite_index_line(line: str, index: int) -> str | None:
    if not line.strip().startswith("index:"):
        return None
    indent = _yaml_indent(line)
    return f"{indent}index: {index}\n"


def _rewrite_file_id_line(line: str, file_id: str) -> str | None:
    if not line.strip().startswith("file_id:"):
        return None
    indent = _yaml_indent(line)
    return f'{indent}file_id: "{file_id}"\n'


def _ensure_file_id(out: list[str], file_id: str, *, had_file_id: bool) -> None:
    if had_file_id:
        return
    if _insert_file_id_after(out, file_id, "index:"):
        return
    _insert_file_id_after(out, file_id, "emoji:")


def _rewrite_block(block: list[str], index: int, file_id: str) -> list[str]:
    """Return the sticker block with index/file_id set, inserting file_id if absent."""
    out: list[str] = []
    had_file_id = False
    for line in block:
        rewritten = _rewrite_index_line(line, index)
        if rewritten is not None:
            out.append(rewritten)
            continue
        rewritten = _rewrite_file_id_line(line, file_id)
        if rewritten is not None:
            out.append(rewritten)
            had_file_id = True
            continue
        out.append(line)
    _ensure_file_id(out, file_id, had_file_id=had_file_id)
    return out


def _consume_block(
    lines: list[str], start: int, base_indent: int
) -> tuple[list[str], int]:
    block = [lines[start]]
    i = start + 1
    n = len(lines)
    while i < n:
        nxt = lines[i]
        if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= base_indent:
            break
        block.append(nxt)
        i += 1
    return block, i


def _emit_block(
    out: list[str],
    block: list[str],
    name: str,
    updates: dict[str, tuple[int, str]],
) -> None:
    if name not in updates:
        out.extend(block)
        return
    index, file_id = updates[name]
    out.extend(_rewrite_block(block, index, file_id))


def apply_updates_to_text(text: str, updates: dict[str, tuple[int, str]]) -> str:
    """Rewrite index/file_id inside the yaml by name, preserving all other content."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("- name:"):
            name = _parse_name(stripped)
            base_indent = len(line) - len(line.lstrip())
            block, i = _consume_block(lines, i, base_indent)
            _emit_block(out, block, name, updates)
            continue
        out.append(line)
        i += 1
    return "".join(out)
