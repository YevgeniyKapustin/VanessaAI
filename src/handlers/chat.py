import json
from random import randint, choice


from vkbottle.bot import Message
from vkbottle.framework.labeler import BotLabeler

from src.rules import DiceRule
from src.services import create_response_json, get_data
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


@bl.message(text='фракция')
async def random_fraction(message: Message):
    """Send a random faction from the hero_fractions."""
    await message.answer(f'🎲 {choice(hero_fractions)}')


@bl.message(DiceRule())
async def roll_dice(message: Message):
    """Send the result from 1 to the number after 'д'."""
    await message.answer(f'🎲 {randint(1, int(message.text.replace("д", "")))}')


@bl.message(text='добавить<type_> команду<request>:<response>')
async def add_command(
        message: Message,
        type_: str,
        request: str,
        response: str
):
    type_ = 'contextual' if type_ == '_' else 'normal'
    if request:
        res = await web_query.create_command(
            type_,
            request,
            await create_response_json(message, response)
        )
        if (msg := res[0].get('message')) == 'Create':
            await message.answer(f'команда "{request}" добавлена')
        else:
            await message.answer(f'вы этого не должны видеть: {msg}')
    elif not request:
        await message.answer(f'не хватает запроса, он пишется перед ":"')


@bl.message(text='<request>')
async def get_command(message: Message, request: str):
    data = json.loads(await get_data(request))
    if data.get('message') or data.get('attch'):
        await message.answer(
            message=data.get('message'),
            attachment=data.get('attch')
        )
