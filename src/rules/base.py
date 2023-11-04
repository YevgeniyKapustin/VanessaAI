"""Модуль для базового правила."""
from abc import ABC, abstractmethod

from src.services.events import Event


class BaseRule(ABC):
    """Абстрактное правило.

    Обязательно определять только метод check, вернуть он должен bool
    Никогда не переопределяйте set_event
    """
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
