"""Public wire-contract surface shared across VanessaAI services."""

from app.contracts.messages import (
    SCHEMA_VERSION,
    BrokerMessage,
    TaskKind,
    TaskMessage,
    TurnImage,
    TurnReply,
    TurnRequest,
    TurnStarted,
)
from app.contracts.version import SCHEMA_VERSION as _SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "BrokerMessage",
    "TurnImage",
    "TurnRequest",
    "TurnStarted",
    "TurnReply",
    "TaskKind",
    "TaskMessage",
]

# Keep the linter honest: version.py is re-exported via messages re-export.
_SCHEMA_VERSION
