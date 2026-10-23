"""Validate a ``hermes_ask`` task payload into a :class:`HermesAsk`."""

from __future__ import annotations

from dataclasses import dataclass

from vanessa.contracts.messages import TaskMessage

# Late follow-ups go through the Telegram adapter only (``OutboundMessage``).
SUPPORTED_CHANNEL = "telegram"


@dataclass(frozen=True, slots=True)
class HermesAsk:
    question: str
    channel: str
    telegram_chat_id: int
    telegram_message_id: int | None
    user_message: str
    #: Hermes ``Idempotency-Key``: the task dedup key, else a stable fallback.
    idempotency_key: str


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _idempotency_key(task: TaskMessage, chat_id: int, message_id: int | None) -> str:
    if task.dedup_key:
        return task.dedup_key
    return f"hermes:{chat_id}:{message_id or task.correlation_id}"


def parse_hermes_ask(task: TaskMessage) -> HermesAsk | None:
    """Return the ask, or None when the payload cannot produce a follow-up."""
    payload = task.payload
    question = str(payload.get("question") or "").strip()
    chat_id = _as_int(payload.get("telegram_chat_id"))
    channel = str(payload.get("channel") or SUPPORTED_CHANNEL)
    if not question or not chat_id or channel != SUPPORTED_CHANNEL:
        return None
    message_id = _as_int(payload.get("telegram_message_id"))
    return HermesAsk(
        question=question,
        channel=channel,
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
        user_message=str(payload.get("user_message") or "").strip(),
        idempotency_key=_idempotency_key(task, chat_id, message_id),
    )
