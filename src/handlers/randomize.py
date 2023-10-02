from random import randint, choice

from src.constants import civilizations, zmiys_phrases, hero_fractions
from src.rules.decorator import handle_message
from src.rules.rules import DiceRule, TextRule
from src.utils.events import Event


@handle_message(TextRule('абоба'))
def handler_random_zmiys_phrases(event: Event):
    event.answer(f'{choice(zmiys_phrases)}')


@handle_message(DiceRule())
def handler_roll_dice(event: Event):
    event.answer(f'🎲 {randint(1, int(event.message.text.replace("д", "")))}')


@handle_message(TextRule('цивилизация'))
def handler_random_civ_from_civ6(event: Event):
    event.answer(f'🎲 {choice(civilizations)}')


@handle_message(TextRule('фракция'))
def handler_random_fraction(event: Event):
    event.answer(f'🎲 {choice(hero_fractions)}')
