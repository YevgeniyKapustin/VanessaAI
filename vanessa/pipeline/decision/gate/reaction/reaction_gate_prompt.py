from __future__ import annotations

import re
from dataclasses import dataclass
from re import Pattern

from vanessa.core.messages import ContextMessage

# Built-in fallback prompt (used only when config/behavior/gate/reaction_gate.yaml does not
# provide ``reaction_gate_prompt``). Kept deliberately tiny: the whole point is a
# single fast, cheap YES/NO call, not a mini-planner.
DEFAULT_REACTION_GATE_PROMPT = (
    'You are a lightweight decision gate for a chat bot "Ванесса" in a group '
    "chat. Decide ONLY whether the bot should react to the CURRENT message.\n"
    "Answer with exactly one word: YES or NO. Nothing else.\n"
    "YES — the message is addressed to the bot, asks a question, requests help, "
    "clearly expects the bot's reaction, or is a short follow-up right after "
    "the bot's own reply demanding more (e.g. \"а ещё\"). "
    'Any imperative addressed to the bot by name or "ты" '
    '("ванесса, не тормози, я написал", "ванесса, отвечай") is an address '
    'to her → YES, even without a question mark. "Общение между собой" means '
    "people talking to each other WITHOUT addressing the bot — naming the bot "
    "is not that.\n"
    "NO — people are simply chatting among themselves; the bot's name was "
    "mentioned in passing but no answer is required; a status remark, a "
    "statement, a rhetorical remark, or small talk that does not call for a "
    "reaction.\n\n"
    "Current message:\n{message}\n\n"
    "Recent messages (before the current one):\n{recent}\n\n"
    "Flags:\n"
    "- the message mentions the bot's name: {mentions_bot}\n"
    "- the message is a reply to the bot's message: {reply_to_bot}\n"
    "- the message is a reply to another user: {reply_to_other_user}\n"
    "- the bot is inside a post-reply window: {listen_window}\n\n"
    "Reply with a single word: YES or NO."
)

# Small built-in imperative request verbs, merged with the configured trigger
# keywords. Used by the zero-cost Tier-1 short-circuit so clear requests
# ("скажи", "напиши", "сделай", ...) never pay an LLM call in the gate.
_IMPERATIVE_REQUESTS = frozenset(
    {
        "скажи",
        "напиши",
        "сделай",
        "дай",
        "покажи",
        "кинь",
        "переведи",
        "объясни",
        "помоги",
        "найди",
        "расскажи",
    }
)
_MAX_RECENT_LINE_CHARS = 200


@dataclass(frozen=True, slots=True)
class ReactionGateResult:
    """Verdict of the lightweight pre-planner classifier.

    ``respond=True`` means the turn proceeds to the heavy LLM planner;
    ``respond=False`` means the pipeline finalizes immediately (the bot stays
    silent) without spending planner/RAG/compose tokens.
    """

    respond: bool
    reason: str = ""


def _word_boundary_pattern(word: str) -> Pattern[str]:
    return re.compile(rf"\b{re.escape(word.strip().lower())}\b", re.IGNORECASE)


def _lower_strip(word: str) -> str:
    return word.strip().lower()


def _format_sender(message: ContextMessage) -> str:
    if message.sender_name:
        return message.sender_name
    if message.sender_telegram_id:
        return f"user{message.sender_telegram_id}"
    return "user"


def _clip_line(text: str) -> str:
    if len(text) <= _MAX_RECENT_LINE_CHARS:
        return text
    return text[:_MAX_RECENT_LINE_CHARS] + "…"


def _format_recent_line(message: ContextMessage) -> str | None:
    text = (message.content or "").replace("\n", " ").strip()
    if not text:
        return None
    text = _clip_line(text)
    if message.role == "assistant":
        return f"[assistant] {text}"
    return f"[{_format_sender(message)}] {text}"


def _recent_lines(recent: list[ContextMessage]) -> list[str]:
    lines: list[str] = []
    for message in recent:
        line = _format_recent_line(message)
        if line is None:
            continue
        lines.append(line)
    return lines


def format_recent_messages(
    recent_messages: list[ContextMessage],
    limit: int,
) -> str:
    """Compact, bounded rendering of the recent window for the classifier.

    Only the tail of the window is used and every line is truncated, so the
    gate call stays tiny and cheap regardless of conversation length.
    """
    recent = recent_messages[-limit:] if limit > 0 else recent_messages
    if not recent:
        return "(нет)"
    return "\n".join(_recent_lines(recent)) or "(нет)"
