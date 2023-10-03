from src.services.events import Event
from src import handlers


class Controller(object):
    __event: Event

    def __init__(self, event):
        self.__event = event

    def recognition(self):
        handlers_modules: list = self.__get_handlers_modules()
        self.__call_handlers(handlers_modules)

    def __call_handlers(self, handlers_modules: list) -> None:
        for handler in handlers_modules:
            handler_args: dict = vars(handler)
            [
                self.__call_handler_funcs(handler_args)
                for module in handlers_modules
                if module is handler
            ]

    def __call_handler_funcs(self, handler_args) -> None:
        [
            handler_args[arg](self.__event)
            for arg in handler_args
            if arg[:8] == 'handler_'
        ]

    @staticmethod
    def __get_handlers_modules() -> list:
        handlers_dir: dict = vars(handlers)
        return [
            handlers_dir[handler_model]
            for handler_model in handlers_dir
            if handler_model[:2] != '__'
        ]
