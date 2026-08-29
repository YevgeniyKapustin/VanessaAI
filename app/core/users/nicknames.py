from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


from app.config.settings import settings
from app.ingest.user_backfill import load_nicknames

_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    # A leading '@' is stripped so a Telegram username (@nu_ya) and its bare form
    # (nu_ya) normalize to the same key.
    return _SPACE_RE.sub(" ", text.replace("ё", "е").lower().lstrip("@")).strip()


def resolve_nicknames_path() -> Path:
    configured = Path(settings.nicknames_config_path)
    if configured.is_file():
        return configured
    project_root = Path(__file__).resolve().parents[2]
    fallback = project_root / "config" / "nicknames.yaml"
    return fallback if fallback.is_file() else configured


@lru_cache
def get_chat_nicknames() -> tuple[str, ...]:
    return tuple(load_nicknames(resolve_nicknames_path()).values())


# ---------------------------------------------------------------------------
# Aliases: the single source of truth is the knowledge vault — each People card
# carries its own frontmatter ``aliases``/``names`` (e.g. «гриша.md» lists both
# «Гриша» and «Ну я»), plus a dedicated ``telegram_username`` field for the TG
# @username (e.g. ``nu_ya`` for ``@nu_ya``). The canonical display name is the
# roster name from ``config/nicknames.yaml`` (by telegram_id) — the same name the
# bot shows as the sender. Editing a People card is enough.
# ---------------------------------------------------------------------------


def _people_dir() -> Path | None:
    """Path to the vault People folder, or None when the vault is unconfigured."""
    raw = settings.knowledge_path.strip() if settings.knowledge_path else ""
    if not raw:
        return None
    root = Path(raw).resolve()
    people = root / "People"
    return people if people.is_dir() else None


def _people_signature() -> tuple:
    """Per-file (path, mtime, size) so People-card edits invalidate the cache."""
    people = _people_dir()
    if people is None:
        return ()
    signature: list = []
    for md in sorted(people.glob("*.md")):
        if md.name == "_index.yaml":
            continue
        try:
            stat = md.stat()
        except OSError:
            continue
        signature.append((md.as_posix(), stat.st_mtime, stat.st_size))
    return tuple(signature)


def _load_vault_aliases() -> dict[str, tuple[str, ...]]:
    """Alias map from the People cards: canonical name -> its aliases.

    For every card the canonical name is the roster name (``config/nicknames.yaml``
    by telegram_id), falling back to the card's ``nickname``/``id``. The aliases
    are the card's frontmatter ``aliases``/``names`` plus the Telegram @username
    (``telegram_username`` / ``username``, e.g. ``nu_ya`` for ``@nu_ya``) minus
    the canonical name itself, deduplicated in order. A leading ``@`` is stripped
    so both ``@nu_ya`` and ``nu_ya`` resolve.
    """
    from app.knowledge.format import parse_frontmatter  # lazy: avoids import cycle

    people = _people_dir()
    if people is None:
        return {}
    roster = load_nicknames(resolve_nicknames_path())
    result: dict[str, tuple[str, ...]] = {}
    for md in sorted(people.glob("*.md")):
        if md.name == "_index.yaml":
            continue
        try:
            meta, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not isinstance(meta, dict):
            continue
        canonical = _canonical_for_card(meta, roster)
        if not canonical:
            continue
        aliases: list[str] = []
        seen: set[str] = set()
        for field in ("aliases", "names"):
            for raw in _as_list(meta.get(field)):
                alias = str(raw).strip()
                key = _normalize(alias)
                if not key or key in seen or key == _normalize(canonical):
                    continue
                seen.add(key)
                aliases.append(alias)
        # Telegram @username — its own frontmatter field (e.g. ``nu_ya`` for
        # ``@nu_ya``). A leading '@' is stripped so the bare username also matches.
        for field in ("telegram_username", "username"):
            username = str(meta.get(field) or "").strip()
            if not username:
                continue
            key = _normalize(username)
            if key and key not in seen and key != _normalize(canonical):
                seen.add(key)
                aliases.append(username)
        if aliases:
            result[canonical] = tuple(aliases)
    return result


def _canonical_for_card(meta: dict, roster: dict[int, str]) -> str:
    """Canonical display name for a People card (roster by telegram_id first)."""
    telegram_id = meta.get("telegram_id")
    if telegram_id is not None:
        try:
            roster_name = roster.get(int(telegram_id))
        except (TypeError, ValueError):
            roster_name = None
        if roster_name:
            return str(roster_name)
    return str(meta.get("nickname") or meta.get("id") or "").strip()


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


_ALIAS_CACHE: tuple[tuple, dict[str, tuple[str, ...]]] | None = None


def get_chat_aliases() -> dict[str, tuple[str, ...]]:
    """Alias map (canonical name -> aliases), cached by People-card mtimes."""
    global _ALIAS_CACHE
    signature = _people_signature()
    if _ALIAS_CACHE is not None and _ALIAS_CACHE[0] == signature:
        return _ALIAS_CACHE[1]
    data = _load_vault_aliases()
    _ALIAS_CACHE = (signature, data)
    return data


def _build_variants(aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Map every normalized name (canonical + aliases) to the canonical name.

    ``"ну я"`` (a Telegram nickname) and ``"Гриша"`` (the name people actually
    use) both map to the canonical ``"Гриша"``. The canonical name itself is
    included so an already-canonical sender resolves to itself.
    """
    variants: dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        variants[_normalize(canonical)] = canonical
        for alias in alias_list:
            variants.setdefault(_normalize(alias), canonical)
    # Fall back to the nicknames roster for canonical names that have no People
    # card: they must still canonicalize to themselves.
    for nickname in get_chat_nicknames():
        variants.setdefault(_normalize(nickname), nickname)
    return variants


def get_canonical_variants() -> dict[str, str]:
    return _build_variants(get_chat_aliases())


def canonical_name_for(alias: str | None) -> str | None:
    """Return the canonical display name for a raw name/alias, or None.

    Resolves any spelling (Telegram nickname, alias, canonical name) to the
    single canonical name the bot uses as the sender label — e.g. ``"ну я"``
    resolves to ``"Гриша"``. Returns None when the name is unknown.
    """
    if not alias or not alias.strip():
        return None
    return get_canonical_variants().get(_normalize(alias))


def find_nicknames_in_text(text: str) -> list[str]:
    normalized_text = _normalize(text)
    if not normalized_text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for nickname in get_chat_nicknames():
        normalized_name = _normalize(nickname)
        if len(normalized_name) < 3:
            continue
        matched = (
            normalized_name in normalized_text
            or any(
                token.startswith(normalized_name)
                for token in normalized_text.split()
            )
        )
        if matched and normalized_name not in seen:
            seen.add(normalized_name)
            found.append(nickname)

    # Also match aliases (e.g. «ну я» -> canonical «Гриша»), so mentions by a
    # nickname the chat actually uses still resolve to the canonical person.
    for alias, canonical in get_canonical_variants().items():
        if len(alias) < 3 or canonical in found:
            continue
        matched = (
            alias in normalized_text
            or any(token.startswith(alias) for token in normalized_text.split())
        )
        if matched and alias not in seen:
            seen.add(alias)
            found.append(canonical)
    return found


def format_nicknames_for_planner() -> str:
    nicknames = get_chat_nicknames()
    if not nicknames:
        return "(не заданы)"
    # Several Telegram accounts can share one display name (e.g. three different
    # users are all «Котгаст»). The planner prompt only needs each name once;
    # the full ID→name mapping still lives in get_chat_nicknames() for mention
    # detection, so detection is unaffected by this dedup.
    unique = dict.fromkeys(nicknames)
    return ", ".join(sorted(unique, key=str.lower))


def format_aliases_for_prompt() -> str:
    """Render the alias map as a compact line list for the compose prompt.

    Only aliases that differ from the canonical name are shown, so the bot knows
    «ну я» and «Гриша» are the same person without repeating the name.
    """
    aliases = get_chat_aliases()
    if not aliases:
        return ""
    lines: list[str] = []
    for canonical in sorted(aliases, key=str.lower):
        # Keep one representative per normalized form so «Ну я» and «ну я» are
        # not shown twice; drop aliases equal to the canonical name itself.
        seen: set[str] = set()
        others: list[str] = []
        for alias in aliases[canonical]:
            key = _normalize(alias)
            if key in seen or key == _normalize(canonical):
                continue
            seen.add(key)
            others.append(alias)
        if not others:
            continue
        lines.append(f"{canonical} = {', '.join(others)}")
    return "\n".join(lines)
