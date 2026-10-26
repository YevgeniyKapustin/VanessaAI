from __future__ import annotations

import asyncio
import logging

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.users.alias_extract import (
    aliases_from_notes,
    telegram_nicknames_from_notes,
)
from vanessa.knowledge.users.alias_extract import (
    normalize_alias as _normalize,
)
from vanessa.knowledge.users.nickname_format import (
    build_variants,
    match_nicknames_in_text,
    render_aliases_for_prompt,
    render_nicknames_for_planner,
)
from vanessa.knowledge.users.people_notes import (
    iter_people_notes_fs as _iter_people_notes_fs,
)
from vanessa.knowledge.users.people_notes import (
    people_signature_fs as _people_signature_fs,
)

logger = logging.getLogger(__name__)


def get_chat_nicknames() -> tuple[str, ...]:
    return tuple(get_chat_aliases())


# ---------------------------------------------------------------------------
# Aliases: the single source of truth is the knowledge vault — each People card
# carries its own frontmatter ``aliases``/``names`` (e.g. «гриша.md» lists both
# «Гриша» and «Ну я»), plus a dedicated ``telegram_username`` field for the TG
# @username (e.g. ``nu_ya`` for ``@nu_ya``). The canonical display name is the
# ``nickname`` or ``id`` in that same card. Editing a People card is enough.
# ---------------------------------------------------------------------------


def _event_loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _iter_people_notes():
    from vanessa.knowledge.store.vault import KnowledgeVault  # noqa: PLC0415

    vault = KnowledgeVault()
    if vault.is_configured:
        return vault.list_notes_sync(PEOPLE)
    return _iter_people_notes_fs()


def _people_signature() -> tuple:
    """Per-note identity so People-card edits invalidate the cache."""
    from vanessa.knowledge.store.vault import KnowledgeVault  # noqa: PLC0415

    vault = KnowledgeVault()
    if vault.is_configured:
        return vault.notes_signature_sync(PEOPLE)
    return _people_signature_fs()


type _IdentityCache = tuple[tuple, dict[str, tuple[str, ...]], dict[int, str]]


def _cache_from_notes(signature: tuple, notes) -> _IdentityCache:
    return signature, aliases_from_notes(notes), telegram_nicknames_from_notes(notes)


async def ensure_people_alias_cache() -> None:
    """Load People aliases on the running loop (Postgres is async-only)."""
    global _ALIAS_CACHE  # noqa: PLW0603 - tests reset this module cache
    from vanessa.knowledge.store.vault import KnowledgeVault  # noqa: PLC0415

    try:
        vault = KnowledgeVault()
        if vault.is_configured:
            signature = await vault.notes_signature(PEOPLE)
            notes = await vault.list_notes(PEOPLE)
        else:
            signature = _people_signature_fs()
            notes = _iter_people_notes_fs()
        _ALIAS_CACHE = _cache_from_notes(signature, notes)
    except Exception:
        logger.exception("people_alias_cache_failed")
        if _ALIAS_CACHE is None:
            _ALIAS_CACHE = ((), {}, {})


_ALIAS_CACHE: _IdentityCache | None = None


def _people_identity_cache() -> _IdentityCache:
    global _ALIAS_CACHE  # noqa: PLW0603 - tests reset this module cache
    if _event_loop_running():
        return ((), {}, {}) if _ALIAS_CACHE is None else _ALIAS_CACHE
    signature = _people_signature()
    if _ALIAS_CACHE is not None and _ALIAS_CACHE[0] == signature:
        return _ALIAS_CACHE
    _ALIAS_CACHE = _cache_from_notes(signature, _iter_people_notes())
    return _ALIAS_CACHE


def get_chat_aliases() -> dict[str, tuple[str, ...]]:
    """Alias map (canonical name -> aliases), cached by People-card mtimes."""
    return _people_identity_cache()[1]


def get_telegram_nicknames() -> dict[int, str]:
    """Telegram IDs and names from the same People-card snapshot as aliases."""
    return _people_identity_cache()[2]


def _build_variants(aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return build_variants(aliases, get_chat_nicknames())


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
    return match_nicknames_in_text(
        text, get_chat_nicknames(), get_canonical_variants()
    )


def format_nicknames_for_planner() -> str:
    return render_nicknames_for_planner(get_chat_nicknames())


def format_aliases_for_prompt() -> str:
    """Render the alias map as a compact line list for the compose prompt.

    Only aliases that differ from the canonical name are shown, so the bot knows
    «ну я» and «Гриша» are the same person without repeating the name.
    """
    return render_aliases_for_prompt(get_chat_aliases())
