from src.constants import wiki_queries
from src.rules.base import BaseRule


class DiceRule(BaseRule):
    def check(self) -> bool:
        sides = self._message.replace('д', '')
        return sides.isdigit() and sides != '0' and self._message[0] == 'д'


class TextRule(BaseRule):
    def __init__(self, message=None):
        self._user_msg = message

    def check(self) -> bool:
        return True if not self._user_msg else self._message == self._user_msg


class InlineTextRule(BaseRule):
    def __init__(self, message):
        self._user_msg = message

    def check(self) -> bool:
        return self._user_msg in self._message


class WikiRule(BaseRule):
    def check(self) -> bool:
        return self._message[:9] in wiki_queries


class AnyRule(BaseRule):
    def check(self) -> bool:
        return True
