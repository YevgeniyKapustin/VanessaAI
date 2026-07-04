import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TriggerResult:
    detected: bool
    keyword: str | None = None


class TriggerKeywordChecker:
    def __init__(self, keywords: tuple[str, ...]) -> None:
        escaped = [re.escape(word) for word in keywords if word]
        self._pattern = (
            re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)
            if escaped
            else None
        )

    def detect(self, text: str) -> TriggerResult:
        if self._pattern is None:
            return TriggerResult(detected=False)
        match = self._pattern.search(text)
        if match is None:
            return TriggerResult(detected=False)
        return TriggerResult(detected=True, keyword=match.group(1).lower())
