from typing import Protocol


class HermesHealthProtocol(Protocol):
    """Health probe for Hermes (the owner's PC agent behind an SSH tunnel)."""

    async def is_online(self) -> bool: ...
