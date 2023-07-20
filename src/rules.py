from vkbottle import ABCRule
from vkbottle.bot import Message


class DiceRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        message = event.text
        sides = message.replace('д', '')
        return sides.isdigit() and sides != '0' and message[0] == 'д'


class TextRule(ABCRule[Message]):
    def __init__(self, text: str):
        self.text = text

    async def check(self, event: Message) -> bool:
        return self.text == event.text.lower()
