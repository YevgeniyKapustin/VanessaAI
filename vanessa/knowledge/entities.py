"""Deterministic participant-mention resolution for context filtering.

The query-composition path historically dumped ALL chat participants (up to
``knowledge_participant_max_people`` × several facts) into every planner prompt,
and the semantic retriever only ever fetched ONE person dossier regardless of
how many people a message mentioned. This module deterministically scans the
current message + the recent window for People-card aliases and returns the
matched card files, so:

- the participants digest injects only mentioned / recently-active people;
- the semantic retriever can pull EVERY mentioned dossier (multi-person),
  bounded, instead of a single arbitrary one.

Mention detection is a cheap exact-alias scan (word-boundary guarded), NOT an
LLM call. It complements the LLM turn planner: the planner decides *whether*
the archive is needed and with what detail; the resolver decides *which*
people cards are relevant.
"""

from __future__ import annotations

import re

from vanessa.config.content import get_question_words
from vanessa.core.messages import ContextMessage

_SPACE_RE = re.compile(r"\s+")

# Explicit "about person X" phrasing (not a bare question): «расскажи про
# крабера», «что там у лича», «как у лича с работой», «кто такой тик так».
_PERSON_PROMPT_RE = re.compile(
    r"(?:расскажи|как\s+у|что\s+там\s+у|что\s+с|кто\s+такой|про\s+|об\s+)",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return _SPACE_RE.sub(" ", (text or "").replace("ё", "е").lower()).strip()


def _question_pattern() -> re.Pattern:
    """Regex over the configured question words (config/content/decision.yaml)."""
    words = sorted(
        {str(word).strip().lower() for word in get_question_words() if str(word).strip()},
        key=len,
        reverse=True,
    )
    if not words:
        return re.compile(r"(?!x)x")
    joined = "|".join(re.escape(word) for word in words)
    return re.compile(rf"(?:^|\s)(?:{joined})\b", re.IGNORECASE)


def _contains_alias(text: str, alias: str) -> bool:
    """Inflection-tolerant alias match against a whole token / token prefix.

    Russian inflects nicknames («крабер» → «крабера», «личь» → «лича»), so a
    strict word-boundary match would miss most real mentions. Instead compare
    the alias (with the trailing soft/hard sign dropped) as a prefix of a token
    in the text. Multi-word aliases («тик так») match as their exact phrase.
    """
    if not alias:
        return False
    if " " in alias:
        return alias in text
    stem = alias.rstrip("ьъ")
    return any(token.startswith(stem) for token in text.split())


def _aliases_map(people_index: dict) -> dict:
    if not isinstance(people_index, dict):
        return {}
    aliases = people_index.get("aliases")
    return aliases if isinstance(aliases, dict) else {}


def _alias_position(tokens: list[str], alias: str) -> int | None:
    """Character offset of the alias in the token list, or None."""
    if " " in alias:
        text = " ".join(tokens)
        idx = text.find(alias)
        return idx if idx >= 0 else None
    stem = alias.rstrip("ьъ")
    offset = 0
    for token in tokens:
        if token.startswith(stem):
            return offset
        offset += len(token) + 1
    return None


def mentioned_people_in_text(
    text: str,
    people_index: dict,
    *,
    min_alias_len: int = 3,
) -> list[str]:
    """People-card files whose alias appears in ``text`` (deduped, text order).

    Only People cards are considered (the index ``aliases`` map). The scan is
    cheap and deterministic — no LLM, no embeddings.
    """
    normalized = _normalize(text)
    if not normalized:
        return []
    tokens = normalized.split()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for alias, entry in _aliases_map(people_index).items():
        if not isinstance(entry, dict):
            continue
        file = entry.get("file")
        if not file or file in seen:
            continue
        key = _normalize(str(alias))
        if len(key) < min_alias_len:
            continue
        position = _alias_position(tokens, key)
        if position is not None:
            seen.add(file)
            matches.append((position, file))
    matches.sort(key=lambda item: item[0])
    return [file for _, file in matches]


def resolve_mentioned_people(
    message: str,
    recent_messages: list[ContextMessage] | None,
    people_index: dict,
    *,
    recent_window: int = 5,
) -> list[str]:
    """People mentioned in the current message, then in the recent window.

    The current message is the strongest signal and always comes first; the
    recent window (conversation continuation, per the sliding-window scheme)
    only fills in people not already named. ``recent_window <= 0`` disables the
    window scan.
    """
    result: list[str] = []
    seen: set[str] = set()
    for file in mentioned_people_in_text(message or "", people_index):
        if file not in seen:
            seen.add(file)
            result.append(file)

    recent = recent_messages or []
    window = recent[-recent_window:] if recent_window > 0 else []
    for msg in window:
        text = str(getattr(msg, "content", "") or "")
        reply = getattr(msg, "reply_to_text", None)
        if reply:
            text += " " + str(reply or "")
        for file in mentioned_people_in_text(text, people_index):
            if file not in seen:
                seen.add(file)
                result.append(file)
    return result


def is_person_focused(text: str) -> bool:
    """True when the message is *about* a person, not a passing name drop.

    A message is person-focused when it asks a question (configured question
    words) or explicitly prompts for a person («расскажи про X», «что там у
    X», «кто такой X»). Used by the retrieve stage to decide whether the
    deterministic resolver may force People retrieval even when the planner
    omitted the ``people`` knowledge index.
    """
    normalized = _normalize(text)
    if not normalized:
        return False
    if _question_pattern().search(normalized):
        return True
    return bool(_PERSON_PROMPT_RE.search(normalized))
