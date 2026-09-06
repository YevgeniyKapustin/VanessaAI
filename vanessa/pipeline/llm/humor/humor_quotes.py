from vanessa.core.messages import ContextBlock, ContextMessage
from vanessa.pipeline.llm.humor.humor_score import _score_candidate
from vanessa.pipeline.llm.humor.humor_score_theme import (
    _normalize,
    _theme_repeat_count,
)


def _user_followup(
    index: int,
    message: ContextMessage,
    messages: list[ContextMessage],
) -> tuple[str, list[ContextMessage]] | None:
    if message.role != "user":
        return None
    text = message.content.strip()
    if not text:
        return None
    return text, messages[index + 1 : index + 3]


def _append_block_candidates(
    block: ContextBlock,
    corpus: list[str],
    candidates: list[tuple[int, int, ContextMessage, list[ContextMessage]]],
) -> None:
    messages = list(block.messages)
    for index, message in enumerate(messages):
        item = _user_followup(index, message, messages)
        if item is None:
            continue
        text, nxt = item
        corpus.append(text)
        candidates.append((index, block.anchor_id, message, nxt))


def _collect_humor_candidates(
    blocks: list[ContextBlock],
) -> tuple[list[str], list[tuple[int, int, ContextMessage, list[ContextMessage]]]]:
    corpus: list[str] = []
    candidates: list[tuple[int, int, ContextMessage, list[ContextMessage]]] = []
    for block in blocks:
        _append_block_candidates(block, corpus, candidates)
    return corpus, candidates


def _maybe_rank_quote(
    message: ContextMessage,
    next_messages: list[ContextMessage],
    corpus: list[str],
    min_score: float,
    seen: set[str],
    ranked: list[tuple[float, str]],
) -> None:
    text = message.content.strip()
    key = _normalize(text)
    if key in seen:
        return
    score = _score_candidate(
        text,
        is_anchor=message.is_anchor,
        next_messages=next_messages,
        theme_repeats=_theme_repeat_count(text, corpus),
    )
    if score < min_score:
        return
    seen.add(key)
    ranked.append((score, text))


def _rank_humor_quotes(
    candidates: list[tuple[int, int, ContextMessage, list[ContextMessage]]],
    corpus: list[str],
    min_score: float,
) -> list[tuple[float, str]]:
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for _, _, message, next_messages in candidates:
        _maybe_rank_quote(
            message, next_messages, corpus, min_score, seen, ranked
        )
    return ranked


def extract_humor_quotes(
    blocks: list[ContextBlock],
    *,
    max_quotes: int = 3,
    min_score: float = 2.5,
) -> list[str]:
    if max_quotes <= 0 or not blocks:
        return []

    corpus, candidates = _collect_humor_candidates(blocks)
    if not corpus:
        return []

    ranked = _rank_humor_quotes(candidates, corpus, min_score)
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in ranked[:max_quotes]]
