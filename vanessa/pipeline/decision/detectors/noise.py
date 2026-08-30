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


class NoiseFilter:
    def __init__(self, heuristics: NoiseHeuristics | None = None) -> None:
        self._rules = heuristics or get_noise_heuristics()
        self._substantive_re = _substantive_pattern()

    def is_noise(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return True
        if _ACK_RE.match(normalized):
            return True
        if self._looks_substantive(normalized):
            return False

        words = normalized.split()
        if (
            len(words) <= self._rules.max_words
            and len(normalized) <= self._rules.max_chars
        ):
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

    def _is_reaction_only(self, text: str) -> bool:
        if len(text) > self._rules.max_chars:
            return False
        for char in text:
            if char.isspace():
                continue
            category = unicodedata.category(char)
            if category.startswith(("P", "S")):
                continue
            if category.startswith(("L", "N")):
                return False
        return bool(text.strip())


@lru_cache
def _substantive_pattern() -> re.Pattern[str] | None:
    words = get_question_words()
    triggers = get_trigger_keywords()
    modals = get_modal_verbs()
    parts: list[str] = []
    if words:
        parts.append(rf"\b({'|'.join(re.escape(w) for w in words)})\b")
    if triggers:
        parts.append(rf"\b({'|'.join(re.escape(w) for w in triggers)})\b")
    if modals:
        modal = "|".join(re.escape(w) for w in modals)
        parts.append(rf"\b({modal})\s+ли\b")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)
