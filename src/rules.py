from vkbottle import ABCRule
from vkbottle.bot import Message


class DiceRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        sides = event.text.replace('д', '')
        return sides.isdigit() and sides != '0'
