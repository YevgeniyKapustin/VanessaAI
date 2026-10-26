"""Render recent messages for the memory planner."""

from __future__ import annotations

from vanessa.core.bot_senders import is_bot_sender_label
from vanessa.core.message_time import format_message_time
from vanessa.core.messages import ContextMessage
from vanessa.knowledge.people.people import canonical_name_for_telegram_id


def _memory_sender_name(message: ContextMessage) -> str:
    nickname = canonical_name_for_telegram_id(message.sender_telegram_id)
    if nickname:
        return nickname
    if message.sender_name:
        return message.sender_name
    if message.sender_telegram_id:
        return str(message.sender_telegram_id)
    return "user"


def _memory_user_line(message: ContextMessage, time_label: str, text: str) -> str:
    sender = _memory_sender_name(message)
    if message.sender_telegram_id is not None:
        return f"{time_label} [user:{sender} (id:{message.sender_telegram_id})] {text}"
    return f"{time_label} [user:{sender}] {text}"


def format_memory_transcript(messages: list[ContextMessage]) -> str:
    """Render recent messages for the memory planner.

    Senders are labelled with their canonical nickname (from
    People-card metadata) and their telegram id, so the planner outputs
    stable ``person`` references that the writer resolves to a single card —
    instead of inventing new spellings like «ну я», «капуст», «владимир».
    """
    lines = [_memory_line(message) for message in messages]
    return "\n".join(line for line in lines if line)


def _memory_line(message: ContextMessage) -> str | None:
    text = message.content.replace("\n", " ").strip()
    if not text:
        return None
    time_label = format_message_time(message.created_at)
    if message.role == "assistant":
        return f"{time_label} [assistant] {text}"
    if is_bot_sender_label(message.sender_name):
        # Other AI bots get no person card: keep them out of memory.
        return None
    return _memory_user_line(message, time_label, text)
