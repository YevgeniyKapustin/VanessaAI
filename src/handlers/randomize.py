from random import randint

from src.rules.decorator import handle_message
from src.rules.dice import DiceRule
from src.utils.events import Event


@handle_message(DiceRule)
def handler_roll_dice(event: Event):
    event.answer(f'🎲 {randint(1, int(event.message.text.replace("д", "")))}')
