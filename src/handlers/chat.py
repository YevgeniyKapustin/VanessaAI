import json
from random import randint, choice

from requests import Response
from vkbottle.bot import Message
from vkbottle.framework.labeler import BotLabeler

from src.session import session
from src.config import settings
from src.constants import civilizations, zmiys_phrases, hero_fractions

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


@bl.message(text='добавить команду <type_> <request>:<response>')
async def add_command(
        message: Message,
        type_: str,
        request: str,
        response: str,
):
    server_response = session.post(
        f'{settings.SERVER_URI}/api/v1/commands',
        json={
          "type": type_.strip(),
          "request": request.strip(),
          "response": response.strip()
        }
    )

    if server_response.status_code == 201:
        await message.answer(f'команда "{request}" была добавлена')


@bl.message(text='<request>')
async def get_command(
        message: Message,
        request: str,
):
    server_response: Response = session.get(
        f'{settings.SERVER_URI}/api/v1/commands',
        params={
            'request_': request
        }
    )

    if server_response.status_code == 200:
        commands: list[dict] = json.loads(server_response.content)

        for command in commands:

            if command.get('request') == request:
                await message.answer(command.get('response'))
                break


@bl.message(text=['д<sides>', 'd<sides>'])
async def roll_dice(message: Message, sides: str | None):
    """Send the result from 1 to the number after 'д' or 'd'."""
    if sides.isdigit() and sides != '0':
        await message.answer(f'🎲 {randint(1, int(sides))}')
