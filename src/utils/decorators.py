from wikipedia import PageError, DisambiguationError, WikipediaException

from src.rules.base import BaseRule
from src.services.events import Event


def handle_message(rule: BaseRule):
    def decorator(func: callable):
        def wrapper(event: Event):
            func(event) if rule.set_event(event).check() else ...
        return wrapper
    return decorator


def wiki_exception_handler(func):

    def wrapper(self):
        try:
            return func(self)
        except PageError:
            return self._handling_page_error()
        except DisambiguationError as error:
            return self._handling_disambiguation(error)
        except WikipediaException:
            return self._handling_wiki_exception()

    return wrapper
