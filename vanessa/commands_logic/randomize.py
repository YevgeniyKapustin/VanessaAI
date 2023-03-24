"""Contains various functions that somehow use random"""
from random import randint

from basic_actions.actions import send_text, send_file
from prepare.connection import Connection

_vk_admin = Connection().vk_admin

zmiysphrases = [
    'эно как',
    'тюй блин',
    'понял, спасибо',
    'кто былое помянет у того хрен отвянет',
    'тут не поспоришь',
    'не ну так-то да',
    'ясненько',
    'сбылась мечта',
    'мечта',
    'сбылась мечта идиота',
    'не ну а чо',
    'хап тьфу',
    'ужас',
    'кошмар',
    'не ну такое'
]
position = [
    'верх лево',
    'верх право',
    'низ лево',
    'низ право'
]
herofractions = [
    'орден порядка',
    'инферно',
    'лесной союз',
    'некрополис',
    'лига теней',
    'академия волшебства',
    'подгорный народ',
    'великая орда'
]


def send_roll_dice(chat_id: int, msg: str) -> str:
    """Sends the result from 1 to the number after 'Д'"""
    digital = msg.replace('д', '')
    if digital.isdigit() and digital != '0':
        return send_text(chat_id, f'🎲 {randint(1, int(digital))}')


def send_random_zmiys_phrases(chat_id: int) -> str:
    """Selects and sends a random phrase of the good person to the chat"""
    return send_text(chat_id, f'{zmiysphrases[randint(0, 14)]}')


def send_random_fraction(chat_id: int) -> str:
    """Sends a random faction from the herofractions"""
    return send_text(chat_id, f'🎲 {herofractions[randint(0, 7)]}')


def send_random_rarity(chat_id: int) -> str:
    """Sends random art with rarity"""
    photos = _vk_admin.photos.get(
        owner_id='-41670861',
        album_id='269289093',
        count=1000
    )
    random_choice = str(photos['items'][randint(0, 999)]['id'])
    return send_file(chat_id, f'photo-41670861_{random_choice}')
