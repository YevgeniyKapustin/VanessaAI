from abc import ABC, abstractmethod

from src.utils.events import Event


class BaseRule(ABC):
    _event: Event | None
    _message: str | None

    def __init__(self, event: Event = None):
        self._event = event
        self._message = self._event.message.text

    @abstractmethod
    def check(self) -> bool:
        ...
