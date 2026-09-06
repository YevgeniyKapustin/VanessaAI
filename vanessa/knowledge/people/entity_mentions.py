"""Deterministic People-card alias matching in message text."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")
_MIN_ALIAS_LEN = 3


def normalize_mention(text: str) -> str:
    return _SPACE_RE.sub(" ", (text or "").replace("ё", "е").lower()).strip()


def contains_alias(text: str, alias: str) -> bool:
    """Inflection-tolerant alias match against a whole token / token prefix.

    Russian inflects nicknames («крабер» → «крабера», «личь» → «лича»), so a
    strict word-boundary match would miss most real mentions. Instead compare
    the alias (with the trailing soft/hard sign dropped) as a prefix of a token
    in the text. Multi-word aliases («тик так») match as their exact phrase.
    """
    if not alias:
        return False
    if " " in alias:
        return alias in text
    stem = alias.rstrip("ьъ")
    return any(token.startswith(stem) for token in text.split())


def aliases_map(people_index: dict) -> dict:
    if not isinstance(people_index, dict):
        return {}
    aliases = people_index.get("aliases")
    return aliases if isinstance(aliases, dict) else {}


def alias_position(tokens: list[str], alias: str) -> int | None:
    """Character offset of the alias in the token list, or None."""
    if " " in alias:
        text = " ".join(tokens)
        idx = text.find(alias)
        return idx if idx >= 0 else None
    stem = alias.rstrip("ьъ")
    offset = 0
    for token in tokens:
        if token.startswith(stem):
            return offset
        offset += len(token) + 1
    return None


def _entry_file(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return None
    file = entry.get("file")
    if not file:
        return None
    return str(file)


def _alias_match_position(
    alias: object, tokens: list[str], min_alias_len: int
) -> int | None:
    key = normalize_mention(str(alias))
    if len(key) < min_alias_len:
        return None
    return alias_position(tokens, key)


def _maybe_add_mention(
    matches: list[tuple[int, str]],
    seen: set[str],
    alias: object,
    entry: object,
    tokens: list[str],
    min_alias_len: int,
) -> None:
    file = _entry_file(entry)
    if file is None or file in seen:
        return
    position = _alias_match_position(alias, tokens, min_alias_len)
    if position is None:
        return
    seen.add(file)
    matches.append((position, file))


def _collect_mention_matches(
    tokens: list[str], people_index: dict, min_alias_len: int
) -> list[str]:
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for alias, entry in aliases_map(people_index).items():
        _maybe_add_mention(matches, seen, alias, entry, tokens, min_alias_len)
    matches.sort(key=lambda item: item[0])
    return [file for _, file in matches]


def mentioned_people_in_text(
    text: str,
    people_index: dict,
    *,
    min_alias_len: int = _MIN_ALIAS_LEN,
) -> list[str]:
    """People-card files whose alias appears in ``text`` (deduped, text order).

    Only People cards are considered (the index ``aliases`` map). The scan is
    cheap and deterministic — no LLM, no embeddings.
    """
    normalized = normalize_mention(text)
    if not normalized:
        return []
    return _collect_mention_matches(normalized.split(), people_index, min_alias_len)


def _ids_match(key: str, alias: object, entry: dict) -> bool:
    alias_key = normalize_mention(str(alias))
    if key == alias_key:
        return True
    person_id = normalize_mention(str(entry.get("id") or ""))
    if not person_id:
        return False
    return key == person_id


def _prefix_stem_match(key: str, alias: object) -> bool:
    stem = normalize_mention(str(alias)).rstrip("ьъ")
    if not stem:
        return False
    return key.startswith(stem)


def _consider_name_alias(
    key: str, alias: object, entry: object, prefix_hit: str | None
) -> tuple[str | None, str | None]:
    file = _entry_file(entry)
    if file is None:
        return prefix_hit, None
    if _ids_match(key, alias, entry):
        return prefix_hit, file
    if prefix_hit is None and _prefix_stem_match(key, alias):
        return file, None
    return prefix_hit, None


def _scan_people_file(key: str, people_index: dict) -> str | None:
    prefix_hit: str | None = None
    for alias, entry in aliases_map(people_index).items():
        prefix_hit, exact = _consider_name_alias(key, alias, entry, prefix_hit)
        if exact:
            return exact
    return prefix_hit


def people_file_for_name(name: str, people_index: dict) -> str | None:
    """People-card file whose alias or id matches ``name``, or None."""
    key = normalize_mention(name)
    if len(key) < _MIN_ALIAS_LEN:
        return None
    return _scan_people_file(key, people_index)
