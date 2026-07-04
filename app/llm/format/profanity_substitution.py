from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.config.content import AppContent

_WORD_CHARS = r"a-zA-Zа-яёА-ЯЁ0-9_"
_TOKEN_PATTERN = re.compile(
    rf"(?<![{_WORD_CHARS}])([а-яё]+(?:-[а-яё]+)?)(?![{_WORD_CHARS}])",
    re.IGNORECASE,
)

_GENDER_GRAMMEMES = frozenset({"masc", "femn", "neut", "anim", "inan"})
_INFLECTION_GRAMMEMES = frozenset(
    {
        "nomn",
        "gent",
        "datv",
        "accs",
        "ablt",
        "loct",
        "voct",
        "sing",
        "plur",
        "masc",
        "femn",
        "neut",
        "past",
        "pres",
        "futr",
        "perf",
        "impf",
        "indc",
        "impr",
        "cond",
        "1per",
        "2per",
        "3per",
        "anim",
        "inan",
        "tran",
        "intr",
        "Actv",
        "Pass",
    }
)


@lru_cache(maxsize=1)
def _get_morph() -> Any:
    from pymorphy3 import MorphAnalyzer

    return MorphAnalyzer()


def _normalize_key(word: str) -> str:
    return word.replace("ё", "е").lower()


class ProfanitySubstitutor:
    def __init__(
        self,
        lemmas: dict[str, str] | None = None,
        invariable: dict[str, str] | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._lemma_map: dict[str, str] = {}
        self._invariable: list[tuple[re.Pattern[str], str]] = []

        if not enabled:
            return

        for placeholder, target in (lemmas or {}).items():
            self._lemma_map[_normalize_key(placeholder)] = target

        ordered_invariable = sorted(
            (invariable or {}).items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for placeholder, target in ordered_invariable:
            pattern = re.compile(
                rf"(?<![{_WORD_CHARS}]){re.escape(placeholder)}"
                rf"(?![{_WORD_CHARS}])",
                re.IGNORECASE,
            )
            self._invariable.append((pattern, target))

    @classmethod
    def from_content(cls, content: AppContent) -> ProfanitySubstitutor:
        profanity = content.profanity
        return cls(
            profanity.lemmas,
            profanity.invariable,
            enabled=profanity.enabled,
        )

    @staticmethod
    def _apply_case(source: str, target: str) -> str:
        if source.isupper():
            return target.upper()
        if source[:1].isupper():
            return target[:1].upper() + target[1:]
        return target

    @staticmethod
    def _extract_grammemes(tag: Any) -> set[str]:
        return set(tag.grammemes) & _INFLECTION_GRAMMEMES

    def _inflect_target(self, source_parse: Any, target_lemma: str) -> str:
        morph = _get_morph()
        grammemes = self._extract_grammemes(source_parse.tag)
        grammeme_sets = (
            grammemes,
            grammemes - _GENDER_GRAMMEMES,
        )
        for grammeme_set in grammeme_sets:
            if not grammeme_set:
                continue
            frozen = frozenset(grammeme_set)
            for target_parse in morph.parse(target_lemma):
                inflected = target_parse.inflect(frozen)
                if inflected is not None:
                    return inflected.word
        return target_lemma

    def _lookup_target_lemma(self, source_parse: Any) -> str | None:
        lemma_key = _normalize_key(source_parse.normal_form)
        return self._lemma_map.get(lemma_key)

    @staticmethod
    def _match_yo_usage(source: str, target: str) -> str:
        if "ё" in source or "Ё" in source:
            return target
        return target.replace("ё", "е").replace("Ё", "Е")

    def _replace_token(self, word: str) -> str:
        morph = _get_morph()
        candidates: list[tuple[int, Any, str]] = []
        for source_parse in morph.parse(word):
            target_lemma = self._lookup_target_lemma(source_parse)
            if target_lemma is None:
                continue
            score = len(self._extract_grammemes(source_parse.tag))
            candidates.append((score, source_parse, target_lemma))

        if not candidates:
            return word

        _, source_parse, target_lemma = max(candidates, key=lambda item: item[0])
        inflected = self._inflect_target(source_parse, target_lemma)
        inflected = self._match_yo_usage(word, inflected)
        return self._apply_case(word, inflected)

    def _replace_invariable(self, text: str) -> str:
        result = text
        for pattern, target in self._invariable:
            result = pattern.sub(
                lambda match, replacement=target: self._apply_case(
                    match.group(0),
                    replacement,
                ),
                result,
            )
        return result

    def apply(self, text: str) -> str:
        if not self._enabled:
            return text
        if not self._lemma_map and not self._invariable:
            return text

        result = self._replace_invariable(text)
        return _TOKEN_PATTERN.sub(
            lambda match: self._replace_token(match.group(1)),
            result,
        )
