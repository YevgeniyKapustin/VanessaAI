"""Prompt/scan formatting over canonical nicknames and aliases."""

from __future__ import annotations

from vanessa.knowledge.users.alias_extract import normalize_alias

_MIN_MATCH_LEN = 3


def build_variants(
    aliases: dict[str, tuple[str, ...]],
    nicknames: tuple[str, ...],
) -> dict[str, str]:
    """Map every normalized name (canonical + aliases) to the canonical name.

    ``"ну я"`` (a Telegram nickname) and ``"Гриша"`` (the name people actually
    use) both map to the canonical ``"Гриша"``. The canonical name itself is
    included so an already-canonical sender resolves to itself.
    """
    variants: dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        variants[normalize_alias(canonical)] = canonical
        for alias in alias_list:
            variants.setdefault(normalize_alias(alias), canonical)
    # Fall back to the nicknames roster for canonical names that have no People
    # card: they must still canonicalize to themselves.
    for nickname in nicknames:
        variants.setdefault(normalize_alias(nickname), nickname)
    return variants


def _mentions_token(normalized_text: str, needle: str) -> bool:
    if needle in normalized_text:
        return True
    return any(token.startswith(needle) for token in normalized_text.split())


def _try_append_nickname(
    found: list[str], seen: set[str], text: str, nickname: str
) -> None:
    normalized_name = normalize_alias(nickname)
    if len(normalized_name) < _MIN_MATCH_LEN:
        return
    if not _mentions_token(text, normalized_name):
        return
    if normalized_name in seen:
        return
    seen.add(normalized_name)
    found.append(nickname)


def _append_nickname_hits(
    found: list[str],
    seen: set[str],
    text: str,
    nicknames: tuple[str, ...],
) -> None:
    for nickname in nicknames:
        _try_append_nickname(found, seen, text, nickname)


def _should_skip_variant(alias: str, canonical: str, found: list[str]) -> bool:
    if len(alias) < _MIN_MATCH_LEN:
        return True
    return canonical in found


def _append_variant_hits(
    found: list[str],
    seen: set[str],
    text: str,
    variants: dict[str, str],
) -> None:
    for alias, canonical in variants.items():
        if _should_skip_variant(alias, canonical, found):
            continue
        if not _mentions_token(text, alias) or alias in seen:
            continue
        seen.add(alias)
        found.append(canonical)


def match_nicknames_in_text(
    text: str,
    nicknames: tuple[str, ...],
    variants: dict[str, str],
) -> list[str]:
    normalized_text = normalize_alias(text)
    if not normalized_text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    _append_nickname_hits(found, seen, normalized_text, nicknames)
    _append_variant_hits(found, seen, normalized_text, variants)
    return found


def render_nicknames_for_planner(nicknames: tuple[str, ...]) -> str:
    if not nicknames:
        return "(не заданы)"
    # Several Telegram accounts can share one display name (e.g. three different
    # users are all «Котгаст»). The planner prompt only needs each name once;
    # the full ID→name mapping still lives in get_chat_nicknames() for mention
    # detection, so detection is unaffected by this dedup.
    unique = dict.fromkeys(nicknames)
    return ", ".join(sorted(unique, key=str.lower))


def _distinct_aliases(canonical: str, alias_list: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    others: list[str] = []
    canonical_key = normalize_alias(canonical)
    for alias in alias_list:
        key = normalize_alias(alias)
        if key in seen or key == canonical_key:
            continue
        seen.add(key)
        others.append(alias)
    return others


def render_aliases_for_prompt(aliases: dict[str, tuple[str, ...]]) -> str:
    """Render the alias map as a compact line list for the compose prompt.

    Only aliases that differ from the canonical name are shown, so the bot knows
    «ну я» and «Гриша» are the same person without repeating the name.
    """
    if not aliases:
        return ""
    lines: list[str] = []
    for canonical in sorted(aliases, key=str.lower):
        others = _distinct_aliases(canonical, aliases[canonical])
        if not others:
            continue
        lines.append(f"{canonical} = {', '.join(others)}")
    return "\n".join(lines)
