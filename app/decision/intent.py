import re
from dataclasses import dataclass

from app.config.content import (
    get_bot_name_aliases,
    get_modal_verbs,
    get_question_words,
)


@dataclass(frozen=True, slots=True)
class IntentResult:
    detected: bool
    has_question: bool = False
    mentions_bot: bool = False


class IntentDetector:
    def __init__(
        self,
        bot_names: tuple[str, ...] | None = None,
        question_words: tuple[str, ...] | None = None,
    ) -> None:
        words = question_words or get_question_words()
        modals = get_modal_verbs()
        word_group = "|".join(re.escape(word) for word in words)
        modal_group = "|".join(re.escape(word) for word in modals)
        modal_pattern = (
            rf"\b({modal_group})\s+ли\b" if modal_group else ""
        )
        question_parts = [r"\?", rf"\b({word_group})\b"]
        if modal_pattern:
            question_parts.append(modal_pattern)
        self._question_re = re.compile(
            "|".join(question_parts),
            re.IGNORECASE,
        )
        names = bot_names if bot_names is not None else get_bot_name_aliases()
        patterns = [rf"\b{re.escape(name)}\b" for name in names if name]
        self._bot_re = (
            re.compile("|".join(patterns), re.IGNORECASE) if patterns else None
        )

    def detect(self, text: str) -> IntentResult:
        has_question = bool(self._question_re.search(text))
        mentions_bot = bool(self._bot_re.search(text)) if self._bot_re else False
        return IntentResult(
            detected=has_question or mentions_bot,
            has_question=has_question,
            mentions_bot=mentions_bot,
        )
