from src.rules.base import BaseRule


def handle_message(rule: BaseRule):
    def decorator(func):
        def wrapper(event):
            if rule.set_event(event).check():
                func(event)
        return wrapper
    return decorator
