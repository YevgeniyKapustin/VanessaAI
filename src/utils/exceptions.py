class CreateCommandException(Exception):
    __slots__ = ('__text',)

    def __init__(self, text: str):
        self.__text = text

    def __str__(self):
        return self.__text

    def errors(self):
        return [{'msg': f'Assertion failed, {self.__text}'}]
