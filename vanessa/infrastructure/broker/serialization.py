"""Encoding/decoding of broker messages to/from stream field maps.

The stream stores each message as a flat map of string fields (the wire
format). ``encode`` flattens a typed message; ``decode`` rebuilds the typed
message from the kind registry, so unknown kinds fail loudly instead of being
silently misparsed.
"""

from __future__ import annotations

from collections.abc import Mapping

from vanessa.contracts.messages import (
    BrokerMessage,
    InboxNoteReply,
    TaskMessage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from vanessa.infrastructure.broker.errors import UnknownMessageKind

_KIND_TO_MODEL: dict[str, type[BrokerMessage]] = {
    model.message_kind(): model
    for model in (
        TurnRequest,
        TurnStarted,
        TurnReply,
        TaskMessage,
        InboxNoteReply,
    )
}


def encode(message: BrokerMessage) -> dict[str, str]:
    """Flatten a typed message into the field map stored in the stream."""
    return {
        "kind": message.message_kind(),
        "message_id": message.message_id,
        "correlation_id": message.correlation_id,
        "reply_to": message.reply_to or "",
        "trace_id": message.trace_id or "",
        "timestamp": message.timestamp.isoformat(),
        "payload": message.model_dump_json(),
    }


def decode(fields: Mapping[str, str | bytes]) -> BrokerMessage:
    """Rebuild a typed message from stream fields.

    Redis stream entries come back with ``bytes`` keys and values; normalize
    them to ``str`` so callers can pass either form.
    """
    normalized: dict[str, str] = {}
    for key, value in fields.items():
        k = key.decode() if isinstance(key, bytes) else str(key)
        normalized[k] = value.decode() if isinstance(value, bytes) else value
    kind = (normalized.get("kind") or "").strip()
    model = _KIND_TO_MODEL.get(kind)
    if model is None:
        raise UnknownMessageKind(kind)
    payload = normalized["payload"]
    return model.model_validate_json(payload)
