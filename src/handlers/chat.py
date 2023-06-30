import json
from random import randint, choice


from vkbottle.bot import Message
from vkbottle.framework.labeler import BotLabeler

from src.services import create_json, get_data
from src.constants import civilizations, zmiys_phrases, hero_fractions
from src.utils import web_query

bl = BotLabeler()


@bl.message(text='цивилизация')
async def random_civ_from_civ6(message: Message):
    """Select and sends a random phrase of the good person to the chat."""
    await message.answer(f'🎲 {choice(civilizations)}')


@bl.message(text='абоба')
async def random_zmiys_phrases(message: Message):
    """Select and sends a random phrase of the good person to the chat."""
    await message.answer(f'{choice(zmiys_phrases)}')


@bl.message(text='фракций')
async def random_fraction(message: Message):
    """Send a random faction from the hero_fractions."""
    await message.answer(f'🎲 {choice(hero_fractions)}')


@bl.message(text='добавить<type_> команду<request>:<response>')
async def add_command(
        message: Message,
        type_: str,
        request: str,
        response: str
):
    await web_query.create_command(
        type_,
        request,
        await create_json(message, response)
    )
    await message.answer(f'команда "{request}" добавлена')


@bl.message(text='<request>')
async def get_command(message: Message, request: str):
    a = await get_data(request)
    data = json.load(a)
    await message.answer(message=data.message, attachment=data.attachements)


@bl.message(text=['д<sides>', 'd<sides>'])
async def roll_dice(message: Message, sides: str | None):
    """Send the result from 1 to the number after 'д' or 'd'."""
    if sides.isdigit() and sides != '0':
        await message.answer(f'🎲 {randint(1, int(sides))}')
