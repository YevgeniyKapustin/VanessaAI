from random import randint, choice

from src.constants import civilizations, zmiys_phrases, hero_fractions
from src.rules.rules import DiceRule, TextRule
from src.services.events import Event
from src.utils.decorators import handle_message


@handle_message(TextRule('абоба'))
def handler_random_zmiys_phrases(event: Event):
    event.text_answer(f'{choice(zmiys_phrases)}')


@handle_message(DiceRule())
def handler_roll_dice(event: Event):
    dice_sides = int(event.message.text.replace("д", ""))
    event.text_answer(f'🎲 {randint(1, dice_sides)}')


@handle_message(TextRule('цивилизация'))
def handler_random_civ_from_civ6(event: Event):
    event.text_answer(f'🎲 {choice(civilizations)}')


@handle_message(TextRule('фракция'))
def handler_random_fraction(event: Event):
    event.text_answer(f'🎲 {choice(hero_fractions)}')
