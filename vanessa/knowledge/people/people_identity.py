"""Transliteration and fuzzy identity matching for person names."""

from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_PARENS_RE = re.compile(r"[()]")
_MIN_PREFIX_LEN = 5

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


def normalize_person_text(text: str) -> str:
    """Lowercase, collapse whitespace, unify ё -> е."""
    return _SPACE_RE.sub(" ", text.replace("ё", "е").lower()).strip()


def without_parens(text: str) -> str:
    """Drop parentheticals: «евгений (капуста)» -> «евгений капуста»."""
    return _SPACE_RE.sub(" ", _PARENS_RE.sub(" ", text)).strip()


def name_variants(text: str) -> set[str]:
    """Variant forms of a reference used for fuzzy alias matching."""
    result: set[str] = set()
    for raw_variant in (
        without_parens(text),
        text.split("(", maxsplit=1)[0].strip(),
    ):
        variant = raw_variant.strip()
        if variant and variant != text:
            result.add(variant)
    return result


def transliterate(text: str) -> str:
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
    return _NON_ALNUM_RE.sub("", transliterate(text))


def identity_tokens(text: str) -> set[str]:
    """Word tokens of an identity, used for fuzzy alias matching.

    ``identity_tokens("Евгений (Капуста)") == {"evgeniy", "kapusta"}`` so a
    reference like "yevgeniy" still lands on the card aliased «Евгений (Капуста)».
    """
    return {token for token in _NON_ALNUM_RE.split(transliterate(text)) if token}


def _levenshtein_row(previous: list[int], ca: str, b: str, i: int) -> list[int]:
    current = [i]
    for j, cb in enumerate(b, start=1):
        substitution = previous[j - 1] + (ca != cb)
        current.append(min(current[-1] + 1, previous[j] + 1, substitution))
    return current


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two short strings (for transliteration noise)."""
    if a == b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        previous = _levenshtein_row(previous, ca, b, i)
    return previous[-1]


def _long_prefix_match(token_a: str, token_b: str) -> bool:
    if len(token_a) < _MIN_PREFIX_LEN or len(token_b) < _MIN_PREFIX_LEN:
        return False
    if token_a.startswith(token_b):
        return True
    return token_b.startswith(token_a)


def _token_pair_similar(token_a: str, token_b: str) -> bool:
    if token_a == token_b:
        return True
    if levenshtein(token_a, token_b) <= 1:
        return True
    return _long_prefix_match(token_a, token_b)


def _any_token_similar(tokens_a: set[str], tokens_b: set[str]) -> bool:
    for token_a in tokens_a:
        for token_b in tokens_b:
            if _token_pair_similar(token_a, token_b):
                return True
    return False


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
    return _any_token_similar(tokens_a, tokens_b)
