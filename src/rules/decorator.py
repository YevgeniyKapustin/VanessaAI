from src.rules.base import BaseRule
from src.utils.events import Event


def handle_message(rule: BaseRule):
    def decorator(func: callable):
        def wrapper(event: Event):
            func(event) if rule.set_event(event).check() else ...
        return wrapper
    return decorator
