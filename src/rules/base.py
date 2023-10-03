from abc import ABC, abstractmethod

from src.services.events import Event


class BaseRule(ABC):
    _event: Event | None
    _message: str | None

    def set_event(self, event: Event):
        self._event = event
        if event:
            self._message = self._event.message.text
        return self

    @abstractmethod
    def check(self) -> bool:
        ...
