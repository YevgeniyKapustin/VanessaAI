"""Public wire-contract surface shared across VanessaAI services."""

from vanessa.contracts.messages import (
    SCHEMA_VERSION,
    BrokerMessage,
    InboxNoteReply,
    TaskKind,
    TaskMessage,
    TurnImage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from vanessa.contracts.version import SCHEMA_VERSION as _SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "BrokerMessage",
    "InboxNoteReply",
    "TaskKind",
    "TaskMessage",
    "TurnImage",
    "TurnReply",
    "TurnRequest",
    "TurnStarted",
]

assert SCHEMA_VERSION == _SCHEMA_VERSION
