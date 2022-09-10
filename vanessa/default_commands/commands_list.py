import json
from links import *
# actually, the data is taken from json,
# this file is only needed to store commands in case of a reset
default_command = [
    {'text_commands': {
        'капуста': 'эхб',
        'змий': 'гений',
        'матвей': 'мегахарош',
        'картошка': 'хороший чел, качественный',
        'влад': 'капустный стратег😎',
        'кейт': 'ඞ',
        'айко': 'ЕНОТЬЯ СИЛА',
        'амогус': 'тутуту',
        'ыыы': 'ыыы',
        'гитхаб': github,
        'github': github
    }},

    {'gifs_commands': {
        'жидкость': gif_hedgehog,
        'рекрут сус': gif_recruit_sus,
        'картошка сус': gif_potato_sus,
        'сус': gif_sus,
        'холод': gif_cold,
        'чопалах': gif_chop
    }},

    {'indirect_gifs_command': {
        'браво': gif_bravo,
        'бесплатн': gif_free,
        'платн': gif_pay,
        'зарплат': gif_salary,
        'модест': gif_modest,
        'вика': gif_bad,
        'вику': gif_bad,
        'викочк': gif_bad
    }},

    {'img_commands': {
        'кринж': img_kringe,
        'резня': img_carnage
    }},

    {'indirect_img_commands': {
        'зомби в топе': img_zombie
    }},

    {'stick_commands': {

    }},
    {'helpfull_commands': {
        'aboba_command': 'абоба',
        'dice_command': 'д',
        'heroes_helper': ['фракция', 'навык'],
        'wiki_command': ['что такое', 'кто такая', 'кто такой'],
        'mute_command': ['мут', 'размут'],
        'add_command': ['добавить команду', 'удалить команду'],
        'cabbagesite': ['статистика игроков', 'статистика фракций']
    }}
]


if __name__ == '__main__':
    with open('../commands.json', 'w') as f:
        json.dump(default_command, f, indent=4)
