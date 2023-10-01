def handle_message(rule):
    def decorator(func):
        def wrapper(event):
            if rule(event).check():
                func(event)
        return wrapper
    return decorator
