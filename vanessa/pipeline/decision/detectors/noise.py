import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from vanessa.config.content import (
    get_content,
    get_modal_verbs,
    get_question_words,
    get_trigger_keywords,
)

_ACK_RE = re.compile(
    r"^(ок|окей|ага|угу|лол|хм|мм|да|нет|\+{1,3}|\.{2,3})$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NoiseHeuristics:
    max_words: int = 1
    max_chars: int = 12


def get_noise_heuristics() -> NoiseHeuristics:
    decision = get_content().decision
    return NoiseHeuristics(
        max_words=decision.noise_max_words,
        max_chars=decision.noise_max_chars,
    )


def _is_empty_or_ack(normalized: str) -> bool:
    if not normalized:
        return True
    return bool(_ACK_RE.match(normalized))


def _is_letter_or_number(char: str) -> bool:
    if char.isspace():
        return False
    category = unicodedata.category(char)
    if category.startswith(("P", "S")):
        return False
    return category.startswith(("L", "N"))


def _has_letter_or_number(text: str) -> bool:
    return any(_is_letter_or_number(char) for char in text)


class NoiseFilter:
    def __init__(self, heuristics: NoiseHeuristics | None = None) -> None:
        self._rules = heuristics or get_noise_heuristics()
        self._substantive_re = _substantive_pattern()

    def is_noise(self, text: str) -> bool:
        normalized = text.strip()
        if _is_empty_or_ack(normalized):
            return True
        if self._looks_substantive(normalized):
            return False
        if self._is_short_noise(normalized):
            return True
        return self._is_reaction_only(normalized)

    def is_definite_noise(self, text: str) -> bool:
        """Unambiguous filler/acknowledgment — safe to hard-drop without an LLM.

        Covers empty text, bare acknowledgments ("ок", "ага", "да", "лол"),
        and punctuation/emoji-only reactions. Short-but-maybe-meaningful
        messages ("го", "хз", "погнали", "стой") are NOT definite noise: they
        are deferred to the neural network when there is doubt instead of being
        hard-dropped by the deterministic prefilter.
        """
        normalized = text.strip()
        if not normalized:
            return True
        if _ACK_RE.match(normalized):
            return True
        return bool(self._is_reaction_only(normalized))

    def _looks_substantive(self, text: str) -> bool:
        if "?" in text:
            return True
        return bool(self._substantive_re.search(text))

    def _is_short_noise(self, normalized: str) -> bool:
        words = normalized.split()
        return (
            len(words) <= self._rules.max_words
            and len(normalized) <= self._rules.max_chars
        )

    def _is_reaction_only(self, text: str) -> bool:
        if len(text) > self._rules.max_chars:
            return False
        if _has_letter_or_number(text):
            return False
        return bool(text.strip())


def _word_boundary_union(words: list[str] | tuple[str, ...] | None) -> str | None:
    if not words:
        return None
    joined = "|".join(re.escape(word) for word in words)
    return rf"\b({joined})\b"


def _modal_li_pattern(modals: list[str] | tuple[str, ...] | None) -> str | None:
    if not modals:
        return None
    modal = "|".join(re.escape(word) for word in modals)
    return rf"\b({modal})\s+ли\b"


def _substantive_parts() -> list[str]:
    parts: list[str] = []
    for part in (
        _word_boundary_union(get_question_words()),
        _word_boundary_union(get_trigger_keywords()),
        _modal_li_pattern(get_modal_verbs()),
    ):
        if part:
            parts.append(part)
    return parts


@lru_cache
def _substantive_pattern() -> re.Pattern[str] | None:
    parts = _substantive_parts()
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)
