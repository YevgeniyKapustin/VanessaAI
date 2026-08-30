"""Canonical person identity resolution for the knowledge vault.

The memory-planner LLM returns free-form ``person`` references (nicknames,
first names, chat handles). Those must collapse onto ONE stable person card,
otherwise the same participant gets several dossiers (e.g. «капуста»,
«капуст» and «Евгений» for the same person).

Sources of truth, in order:

1. The ``People/_index.yaml`` manifest — existing cards with their
   ``id`` / ``aliases`` / ``telegram_id``.
2. ``config/nicknames.yaml`` — the canonical roster ``telegram_id -> nickname``.

The writer resolves every update's ``person`` through :func:`canonicalize_person`
before choosing the card file, so duplicate spellings never create new cards.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache

from vanessa.infrastructure.ingest.user_backfill import load_nicknames
from vanessa.knowledge.format import slugify
from vanessa.knowledge.users.nicknames import get_chat_nicknames, resolve_nicknames_path

logger = logging.getLogger(__name__)

_SPACE_RE = re.compile(r"\s+")
_PARENS_RE = re.compile(r"[()]")

# Cyrillic -> Latin transliteration used for identity matching. Folding every
# Cyrillic letter to a Latin key unifies «Евгений» with «Yevgeniy» and makes
# mixed-script homoglyph spellings like «kоtgast» (Cyrillic о) equal to
# «котгаст» — the writer must collapse these onto ONE person card.
_CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}
_CYRILLIC_TRANS = {ord(ch): rep for ch, rep in _CYRILLIC_TO_LATIN.items()}
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, unify ё -> е."""
    return _SPACE_RE.sub(" ", text.replace("ё", "е").lower()).strip()


def _without_parens(text: str) -> str:
    """Drop parentheticals: «евгений (капуста)» -> «евгений капуста»."""
    return _SPACE_RE.sub(" ", _PARENS_RE.sub(" ", text)).strip()


def _variants(text: str) -> set[str]:
    """Variant forms of a reference used for fuzzy alias matching."""
    result: set[str] = set()
    for variant in (_without_parens(text), text.split("(")[0].strip()):
        variant = variant.strip()
        if variant and variant != text:
            result.add(variant)
    return result


def _transliterate(text: str) -> str:
    """Lowercase, Cyrillic->Latin, then strip Latin diacritics.

    The Cyrillic table runs FIRST so «й» -> "y" and «ё» -> "e" keep their
    dedicated mapping (NFKD would decompose «й» into «и»+breve and change the
    transliteration). NFKD is then applied to the Latin result only, which folds
    diacritics like «ś» into "s" so they survive the ASCII identity filter
    instead of being lost.
    """
    translit = text.lower().translate(_CYRILLIC_TRANS)
    folded = unicodedata.normalize("NFKD", translit).lower()
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def identity_key(text: str) -> str:
    """Compact ASCII key for a name/handle (spaces and punctuation dropped).

    ``identity_key("Евгений (Капуста)") == identity_key("Yevgeniy")``-ish: both
    fold to "evgeniykapusta", so Latin transliterations and mixed-script
    homoglyphs resolve to the same card.
    """
    return _NON_ALNUM_RE.sub("", _transliterate(text))


def identity_tokens(text: str) -> set[str]:
    """Word tokens of an identity, used for fuzzy alias matching.

    ``identity_tokens("Евгений (Капуста)") == {"evgeniy", "kapusta"}`` so a
    reference like "yevgeniy" still lands on the card aliased «Евгений (Капуста)».
    """
    return {token for token in _NON_ALNUM_RE.split(_transliterate(text)) if token}


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two short strings (for transliteration noise)."""
    if a == b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def identity_similar(a: str, b: str) -> bool:
    """True when two identities likely denote the same person.

    Matches on any shared token (exact), a single-transcription-error token
    (edit distance <= 1), or a long prefix (the LLM often appends a handle to a
    name, e.g. «modest» -> «modestyar»).
    """
    tokens_a = identity_tokens(a)
    tokens_b = identity_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    for token_a in tokens_a:
        for token_b in tokens_b:
            if token_a == token_b:
                return True
            if levenshtein(token_a, token_b) <= 1:
                return True
            if (
                len(token_a) >= 5
                and len(token_b) >= 5
                and (token_a.startswith(token_b) or token_b.startswith(token_a))
            ):
                return True
    return False


@lru_cache
def _nickname_map() -> dict[int, str]:
    return load_nicknames(resolve_nicknames_path())


def canonical_name_for_telegram_id(telegram_id: int | None) -> str | None:
    """Canonical nickname from ``config/nicknames.yaml`` for a telegram id."""
    if telegram_id is None:
        return None
    return _nickname_map().get(telegram_id)


def telegram_id_for_slug(slug: str) -> int | None:
    """Reverse ``config/nicknames.yaml`` lookup: canonical slug -> telegram id."""
    for telegram_id, nickname in _nickname_map().items():
        if slugify(nickname) == slug:
            return telegram_id
    return None


def _entry_id(value: object) -> str:
    """Extract the ``id`` from an index entry dict, or an empty string."""
    if isinstance(value, dict):
        note_id = value.get("id")
        if note_id is not None:
            return str(note_id)
    return ""


def canonicalize_person(
    person: str,
    telegram_id: int | None,
    people_index: dict | None,
) -> str:
    """Map a free-form person reference to a stable person-card id.

    Resolution order:

    1. ``telegram_id`` -> existing People card (index ``telegram_id`` map).
    2. name / alias / id -> existing People card (index ``aliases`` map),
       trying the exact reference, then fuzzy variants (no parentheticals,
       stem before ``(``) on both the reference and the alias keys.
    3. canonical nickname from ``config/nicknames.yaml``.
    4. fallback: slugify the reference (a brand-new card).

    Returns an empty string when the reference is blank.
    """
    reference = _normalize(person)
    if not reference:
        return ""
    index = people_index or {}
    alias_map = index.get("aliases")
    telegram_map = index.get("telegram_id")
    alias_map = alias_map if isinstance(alias_map, dict) else {}
    telegram_map = telegram_map if isinstance(telegram_map, dict) else {}

    # 1) telegram id is the strongest, unambiguous signal.
    if telegram_id is not None:
        card_id = _entry_id(telegram_map.get(str(telegram_id)))
        if card_id:
            return card_id

    # Normalize both sides once (index keys are lowercased but not ё -> е).
    normalized_aliases = {
        _normalize(str(key)): entry for key, entry in alias_map.items()
    }
    normalized_telegrams = {
        str(key): entry for key, entry in telegram_map.items()
    }

    # 2) exact alias / id match, or a raw telegram-id reference.
    if reference.isdigit():
        card_id = _entry_id(normalized_telegrams.get(reference))
        if card_id:
            return card_id
    card_id = _entry_id(normalized_aliases.get(reference))
    if card_id:
        return card_id

    # 2b) fuzzy variants: compare variant forms of the reference and of every
    # alias, so «евгений капуста» still lands on the card aliased
    # «Евгений (Капуста)» (and vice versa).
    variant_to_entry: dict[str, str] = {}
    for alias, entry in normalized_aliases.items():
        entry_id = _entry_id(entry)
        if not entry_id:
            continue
        for variant in _variants(alias):
            variant_to_entry.setdefault(variant, entry_id)
    card_id = variant_to_entry.get(reference) or ""
    if not card_id:
        for variant in _variants(reference):
            card_id = variant_to_entry.get(variant) or ""
            if card_id:
                break
    if card_id:
        return card_id

    # 2c) identity matching: Latin transliterations, Cyrillic homoglyphs and
    # near-name spellings («yevgeniy», «begemot», «kоtgast», «modestyar»)
    # collapse onto the existing card instead of creating a new one.
    reference_key = identity_key(reference)
    for alias, entry in normalized_aliases.items():
        entry_id = _entry_id(entry)
        if not entry_id:
            continue
        if identity_key(alias) == reference_key or identity_similar(reference, alias):
            return entry_id

    # 3) canonical roster from config/nicknames.yaml.
    for nickname in get_chat_nicknames():
        normalized_nickname = _normalize(nickname)
        if normalized_nickname == reference:
            return slugify(nickname)
        if reference in _variants(normalized_nickname):
            return slugify(nickname)
        if identity_key(nickname) == reference_key or identity_similar(reference, nickname):
            return slugify(nickname)

    # 4) fallback: treat the reference as a brand-new person. A new card is an
    # anomaly (every chat participant has a canonical nickname), so log it.
    logger.warning(
        "knowledge_new_person_card created=%s reference=%r telegram_id=%s",
        slugify(person),
        person,
        telegram_id,
    )
    return slugify(person)
