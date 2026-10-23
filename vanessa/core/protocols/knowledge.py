from typing import Protocol

from vanessa.core.knowledge_dto import KnowledgeBlock


class PinnedNotesProtocol(Protocol):
    """Vault notes that go into the compose prompt on every reply."""

    async def blocks(self) -> list[KnowledgeBlock]: ...
