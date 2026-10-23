from typing import Protocol

from vanessa.core.reminders import NewReminder, Reminder


class ReminderStoreProtocol(Protocol):
    """Per-chat reminder storage used by the turn pipeline."""

    async def add(self, new: NewReminder) -> Reminder: ...

    async def list_for_chat(self, chat_id: int) -> list[Reminder]: ...

    async def delete(self, chat_id: int, ids: list[int]) -> int: ...
