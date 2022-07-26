from vanessa.actions import send_text
from random import randint
from vanessa.commands_list import dice_command

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


def send_roll_dice(chat_id, msg):
    if msg.replace(dice_command, '').isdigit() and msg.replace(dice_command, '') != '0':
        return send_text(chat_id, f'🎲 {randint(1, int(msg.replace(dice_command, "")))}')


def send_random_zmiysphrases(chat_id):
    return send_text(chat_id, f'{zmiysphrases[randint(0, 14)]}')


def send_random_position(chat_id):
    return send_text(chat_id, f'🎲 {position[randint(0, 3)]}')


def send_random_fraction(chat_id):
    return send_text(chat_id, f'🎲 {herofractions[randint(0, 7)]}')
