"""Декораторы."""
from wikipedia import PageError, DisambiguationError, WikipediaException

from src.rules.base import BaseRule
from src.services.events import Event


def handle_message(rule: BaseRule):
    """Вызывает функцию, к которой прикреплен, если её правило сработало."""
    def decorator(func: callable):
        def wrapper(event: Event):
            func(event) if rule.set_event(event).check() else ...
        return wrapper
    return decorator


def wiki_exception_handler(func: callable) -> callable:
    """Декоратор для обработки ошибок библиотеки wikipedia.
    Пригоден только для использования внутри объекта Wikipedia из services.

    """
    def wrapper(self):
        try:
            return func(self)

        except PageError:
            return self._handling_page_error()

        except DisambiguationError as error:
            options: set[str] = set()
            for var in error.args[1]:
                if '«' in var and '»' in var:
                    var = var.replace('«', '').replace('»', '')
                options.add(var)
            if len(options) < 2:  # Должно быть хотя бы 2 варианта ответа
                return self._handling_wiki_exception()
            return self._handling_disambiguation(error)

        except WikipediaException:
            return self._handling_wiki_exception()

    return wrapper
