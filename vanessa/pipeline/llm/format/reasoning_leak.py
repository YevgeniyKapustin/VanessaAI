"""Tell a clean untagged reply from leaked reasoning.

The composer is told to think, then write ``[answer]`` and the message. In
thinking mode (DeepSeek ``reasoning_effort``) the API returns the chain of
thought in ``reasoning_content``, apart from ``content``. The model then
often drops the tag, but ``content`` is already the clean message. So a
missing tag alone is not a leak.

A leak is text about the reply instead of the reply itself: «Он просто
зовёт по имени. Отвечаю сухо», an English plan («He asks… I should…»),
or prompt/planner words. Only such text is retried and then silenced.
"""

from __future__ import annotations

import re

from vanessa.pipeline.llm.format.answer_tag import is_untagged_reply
from vanessa.pipeline.llm.format.code_fences import FENCED_CODE

# Below this many letters the Latin share says nothing.
MIN_LETTERS = 20
# More Latin than this among the letters: an English chain of thought.
MAX_LATIN_SHARE = 0.5

_FLAGS = re.IGNORECASE
_LEAK_PATTERNS = (
    # Vanessa plans her own reply, as a sentence: «Отвечаю сухо», «Ответить
    # по делу», «Не упоминать…», «Разбить на блоки». Mid-sentence «отвечу по
    # делу» is a normal reply.
    re.compile(
        r"(?:^|[.!?:\n]\s*)(?:отвеч(?:аю|у)\s+(?:сухо|коротко|кратко|нейтрально"
        r"|в\s+тон|по\s+делу|одн(?:ой|им)|без\s|с\s+подкол)"
        r"|(?:не\s+)?(?:ответить|упомянуть|упоминать|перечислять|пересказывать"
        r"|раскрывать|разбить|составить|перегружать)\b)",
        _FLAGS,
    ),
    # The output opens by narrating the message: «Миша просит рассказать…».
    re.compile(
        r"^\s*[\w-]+\s+(?:\w+\s+)?(?:просит|спрашивает|зов[её]т)\s",
        _FLAGS,
    ),
    re.compile(r"\b(?:перескажу|переформулирую|сформулирую)\b", _FLAGS),
    re.compile(
        r"\b(?:надо|нужно|стоит|лучше|следует)\s+(?:бы\s+)?"
        r"(?:ответить|отвечать|промолчать|написать\s+(?:ему|ей|коротко))\b",
        _FLAGS,
    ),
    # Third person about the sender: «он просто зовёт по имени».
    re.compile(
        r"\b(?:он|она|пользователь|юзер|собеседник)\s+(?:\w+\s+)?"
        r"(?:зов[её]т\s+(?:меня|по\s+имени)|спрашивает\s+(?:меня|про|о|об|что|как)"
        r"|просит\s+(?:меня|рассказать|поставить)|обращается\s+ко\s+мне)",
        _FLAGS,
    ),
    # English chain of thought.
    re.compile(
        r"\b(?:the\s+user|he\s+asks|she\s+asks|he's\s+asking|she's\s+asking"
        r"|i\s+should|i\s+need\s+to|let\s+me|in\s+character|first\s+person)\b",
        _FLAGS,
    ),
    # Prompt and planner words.
    re.compile(
        r"\b(?:should_reply|hermes_query|ask_hermes|reasoning_content)\b"
        r"|\[\s*reasoning\s*\]|\bсистемн\w*\s+промпт",
        _FLAGS,
    ),
)
# Parts that are not prose: links, inline code, control tags.
_NOT_PROSE = re.compile(r"https?://\S+|`[^`]*`|\[[^\]\n]{0,40}\]")
_LETTER = re.compile(r"[^\W\d_]")
_LATIN = re.compile(r"[a-zA-Z]")


def _latin_share(text: str) -> float:
    prose = _NOT_PROSE.sub(" ", FENCED_CODE.sub(" ", text))
    letters = _LETTER.findall(prose)
    if len(letters) < MIN_LETTERS:
        return 0.0
    return sum(1 for char in letters if _LATIN.match(char)) / len(letters)


def looks_like_reasoning(text: str) -> bool:
    """True for text about the reply (a plan, a note on the sender), not a reply."""
    if any(pattern.search(text) for pattern in _LEAK_PATTERNS):
        return True
    return _latin_share(text) > MAX_LATIN_SHARE


def is_reasoning_leak(raw: str) -> bool:
    """Untagged output that reads as reasoning: never send it to the chat.

    Untagged output that reads as a clean reply is the answer.
    """
    return is_untagged_reply(raw) and looks_like_reasoning(raw)


__all__ = ["is_reasoning_leak", "looks_like_reasoning"]
