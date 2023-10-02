from src.constants import wiki_queries
from src.rules.base import BaseRule


class DiceRule(BaseRule):
    def check(self) -> bool:
        message = self._message
        sides = message.replace('д', '')
        return sides.isdigit() and sides != '0' and message[0] == 'д'


class TextRule(BaseRule):
    def __init__(self, message):
        self._user_msg = message

    def check(self) -> bool:
        return self._message == self._user_msg


class WikiRule(BaseRule):
    def check(self) -> bool:
        return self._message[:9] in wiki_queries
