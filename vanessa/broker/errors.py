"""Broker error types."""


class BrokerError(Exception):
    """Base class for broker transport errors."""


class BrokerTimeoutError(BrokerError):
    """An RPC request did not receive its reply within the configured timeout."""


class UnknownMessageKind(BrokerError):
    """A stream entry carried an unknown/unsupported message kind."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"unknown broker message kind: {kind!r}")
