from src.rules.base import BaseRule


class DiceRule(BaseRule):
    def check(self) -> bool:
        message = self._message
        sides = message.replace('д', '')
        return sides.isdigit() and sides != '0' and message[0] == 'д'
