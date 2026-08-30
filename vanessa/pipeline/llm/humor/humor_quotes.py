import re

from vanessa.core.messages import ContextBlock, ContextMessage

_TOKEN = re.compile(r"[a-zа-яё]{4,}", re.IGNORECASE)
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
_STOP = frozenset(
    {
        "этот",
        "этого",
        "тебе",
        "тебя",
        "меня",
        "вообще",
        "просто",
        "очень",
        "когда",
        "потому",
        "сначала",
    }
)


def _normalize(text: str) -> str:
    return text.replace("ё", "е").lower().strip()


def _distinctive_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(_normalize(text))
        if token not in _STOP
    }


def _theme_repeat_count(text: str, corpus: list[str]) -> int:
    tokens = _distinctive_tokens(text)
    if not tokens:
        return 0

    repeats = 0
    for other in corpus:
        if other == text:
            continue
        other_tokens = _distinctive_tokens(other)
        overlap = tokens & other_tokens
        if len(overlap) >= 2:
            repeats += 1
            continue
        if len(tokens) == 1 and overlap:
            repeats += 1
            continue
        for token in tokens:
            if len(token) >= 6 and token in _normalize(other):
                repeats += 1
                break
    return repeats


def _has_reaction(next_messages: list[ContextMessage]) -> bool:
    for follow in next_messages[:2]:
        if follow.role != "user":
            continue
        follow_text = follow.content.strip()
        if _REACTION.search(follow_text) or _HUMOR_IN_TEXT.search(follow_text):
            return True
    return False


def _score_candidate(
    text: str,
    *,
    is_anchor: bool,
    next_messages: list[ContextMessage],
    theme_repeats: int,
) -> float:
    normalized = text.strip()
    if len(normalized) < 12 or len(normalized) > 150:
        return -10.0

    score = 0.0
    if _GENERIC_INSULT.search(normalized):
        score -= 4.0
    if _BORING.search(normalized):
        score -= 4.0
    if _GREETING.search(normalized):
        score -= 5.0
    if _HUMOR_IN_TEXT.search(normalized):
        score += 2.0
    if _RUNNING_JOKE.search(normalized):
        score += 5.0
    if _ABSURD.search(normalized):
        score += 3.0
    if 25 <= len(normalized) <= 100:
        score += 1.5
    elif len(normalized) > 110:
        score -= 1.5
    if is_anchor:
        score += 0.5

    reacted = _has_reaction(next_messages)
    if reacted:
        score += 3.0

    if theme_repeats >= 3:
        score += 5.0
    elif theme_repeats >= 2:
        score += 4.0
    elif theme_repeats == 1:
        score += 2.0
    elif not reacted and not _ABSURD.search(normalized) and not _RUNNING_JOKE.search(
        normalized
    ):
        score -= 3.0

    return score


def extract_humor_quotes(
    blocks: list[ContextBlock],
    *,
    max_quotes: int = 3,
    min_score: float = 2.5,
) -> list[str]:
    if max_quotes <= 0 or not blocks:
        return []

    corpus: list[str] = []
    candidates: list[tuple[int, int, ContextMessage, list[ContextMessage]]] = []

    for block in blocks:
        messages = list(block.messages)
        for index, message in enumerate(messages):
            if message.role != "user":
                continue
            text = message.content.strip()
            if not text:
                continue
            corpus.append(text)
            candidates.append(
                (
                    index,
                    block.anchor_id,
                    message,
                    messages[index + 1 : index + 3],
                )
            )

    if not corpus:
        return []

    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()

    for _, _, message, next_messages in candidates:
        text = message.content.strip()
        key = _normalize(text)
        if key in seen:
            continue
        score = _score_candidate(
            text,
            is_anchor=message.is_anchor,
            next_messages=next_messages,
            theme_repeats=_theme_repeat_count(text, corpus),
        )
        if score >= min_score:
            seen.add(key)
            ranked.append((score, text))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in ranked[:max_quotes]]
