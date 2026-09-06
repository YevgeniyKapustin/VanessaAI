# Cyrillic in regexes matches Russian chat text (RUF001 confusables are intentional).
import re

from vanessa.core.messages import ContextMessage

_HUMOR_IN_TEXT = re.compile(
    r"ахах|аха+|лол|lol|мем|шутк|пошутил|кринж|based|топ|база|кек",
    re.IGNORECASE,
)
_REACTION = re.compile(
    r"^(ахах|аха+|лол|\+{1,3}|согл|пипец|база|based|кек|ор)",
    re.IGNORECASE,
)
_GENERIC_INSULT = re.compile(
    r"^ты\s+(просто\s+)?(лох|долба[её]б|дебил|идиот|тупой|даун|урод)",
    re.IGNORECASE,
)
_RUNNING_JOKE = re.compile(
    r"найди\s+работ|капуст\w*\s+найди|лич\w*\s+найди|"
    r"в\s+тик\s*токе\s+сила|белая\s+ворона|"
    r"я\s+крабер,\s+этот\s+чел|принимаю\s+тебя\s+турбовладислав|"
    r"примитив\w*\s+.*пещер|крабер.*веществ",
    re.IGNORECASE,
)
_ABSURD = re.compile(
    r"пещер|веществ|примитив|принимаю\s+тебя|"
    r"ебать|ёбать|крабер|турбовладислав",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(привет|здарова|здорова|ку|хай|добрый|доброе|салют)\b",
    re.IGNORECASE,
)
_BORING = re.compile(
    r"^(я\s+)?(чисто|просто|ну)\s+(из\s+за|потому)|"
    r"^я\s+пересекла|физручка|долго\s+играть|"
    r"^паблики\s|ко\s+мне\s+сначала",
    re.IGNORECASE,
)
_MIN_QUOTE_CHARS = 12
_MAX_QUOTE_CHARS = 150
_SWEET_MIN_CHARS = 25
_SWEET_MAX_CHARS = 100
_LONG_QUOTE_CHARS = 110
_THEME_REPEATS_HIGH = 3
_THEME_REPEATS_MED = 2


def _pattern_penalties(normalized: str) -> float:
    score = 0.0
    if _GENERIC_INSULT.search(normalized):
        score -= 4.0
    if _BORING.search(normalized):
        score -= 4.0
    if _GREETING.search(normalized):
        score -= 5.0
    return score


def _pattern_bonuses(normalized: str) -> float:
    score = 0.0
    if _HUMOR_IN_TEXT.search(normalized):
        score += 2.0
    if _RUNNING_JOKE.search(normalized):
        score += 5.0
    if _ABSURD.search(normalized):
        score += 3.0
    return score


def _pattern_score(normalized: str) -> float:
    return _pattern_penalties(normalized) + _pattern_bonuses(normalized)


def _length_bonus(length: int) -> float:
    if length > _LONG_QUOTE_CHARS:
        return -1.5
    if _SWEET_MIN_CHARS <= length <= _SWEET_MAX_CHARS:
        return 1.5
    return 0.0


def _follow_is_reaction(follow: ContextMessage) -> bool:
    if follow.role != "user":
        return False
    follow_text = follow.content.strip()
    if _REACTION.search(follow_text):
        return True
    return bool(_HUMOR_IN_TEXT.search(follow_text))


def _has_reaction(next_messages: list[ContextMessage]) -> bool:
    return any(_follow_is_reaction(follow) for follow in next_messages[:2])


def _theme_repeat_hits(theme_repeats: int) -> float | None:
    if theme_repeats >= _THEME_REPEATS_HIGH:
        return 5.0
    if theme_repeats >= _THEME_REPEATS_MED:
        return 4.0
    if theme_repeats == 1:
        return 2.0
    return None


def _lonely_theme_penalty(*, reacted: bool, normalized: str) -> bool:
    if reacted:
        return False
    if _ABSURD.search(normalized):
        return False
    return not _RUNNING_JOKE.search(normalized)


def _theme_repeat_bonus(
    theme_repeats: int,
    *,
    reacted: bool,
    normalized: str,
) -> float:
    hits = _theme_repeat_hits(theme_repeats)
    if hits is not None:
        return hits
    if _lonely_theme_penalty(reacted=reacted, normalized=normalized):
        return -3.0
    return 0.0


def _out_of_quote_range(normalized: str) -> bool:
    return len(normalized) < _MIN_QUOTE_CHARS or len(normalized) > _MAX_QUOTE_CHARS


def _score_candidate(
    text: str,
    *,
    is_anchor: bool,
    next_messages: list[ContextMessage],
    theme_repeats: int,
) -> float:
    normalized = text.strip()
    if _out_of_quote_range(normalized):
        return -10.0

    score = _pattern_score(normalized) + _length_bonus(len(normalized))
    if is_anchor:
        score += 0.5

    reacted = _has_reaction(next_messages)
    if reacted:
        score += 3.0

    return score + _theme_repeat_bonus(
        theme_repeats,
        reacted=reacted,
        normalized=normalized,
    )
