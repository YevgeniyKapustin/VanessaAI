"""Модуль для записи новых правил.

Здесь нужно добавлять свои правила, можете использовать как пример
существующие.
"""
from src.utils.constants import wiki_queries
from src.rules.base import BaseRule


class Dice(BaseRule):
    def check(self) -> bool:
        sides: str = self._message.replace('д', '')
        return sides.isdigit() and sides != '0' and self._message[0] == 'д'


class Text(BaseRule):
    def __init__(self, message: str = None):
        self._user_msg: str = message

    def check(self) -> bool:
        return True if not self._user_msg else self._message == self._user_msg


class InlineText(BaseRule):
    def __init__(self, message: str):
        self._user_msg: str = message

    def check(self) -> bool:
        return self._user_msg in self._message


class Wiki(BaseRule):
    def check(self) -> bool:
        return self._message[:9] in wiki_queries


class Any(BaseRule):
    def check(self) -> bool:
        return True


class Prefix(BaseRule):
    def __init__(self, prefix: str = None):
        self.__prefix: str = prefix

    def check(self) -> bool:
        return self.__prefix in self._message[:len(self.__prefix)]
