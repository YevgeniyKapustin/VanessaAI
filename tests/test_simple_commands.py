from vanessa import navigation
from vanessa.commands_logic.randomize import *
from vanessa.links import *
import pytest
test_chat_id = 4
banan = 'Бана́н — название съедобных плодов культивируемых растений рода Банан (Musa); обычно под таковыми понимают Musa acuminata и Musa × paradisiaca, а также Musa balbisiana, Musa fehi, Musa troglodytarum и ряд других. Также бананами могут называть плоды Ensete ventricosum (строго говоря, являющегося представителем другого рода семейства Банановые). С ботанической точки зрения банан является ягодой, многосеменной и толстокожей.'
simple_commands = [
    (test_chat_id, 'капуста', 'эхб'),
    (test_chat_id, 'сус', gif_sus),
    (test_chat_id, 'бесплатно', gif_free),
    (test_chat_id, 'резня', img_carnage),
    (test_chat_id, 'зомби в топе', img_zombie),
]


@pytest.mark.parametrize('chat_id, command, expect_response', simple_commands)
def test_simple_commands(chat_id, command, expect_response):
    assert navigation.response_definition(chat_id, command, 0, 0) == expect_response


@pytest.mark.parametrize('chat_id, command', [(test_chat_id, 'абоба')])
def test_complex_commands(chat_id, command):
    assert navigation.response_definition(chat_id, command, 0, 0) in zmiysphrases


@pytest.mark.parametrize('chat_id, command', [(test_chat_id, 'д12')])
def test_dice(chat_id, command):
    response = int(navigation.response_definition(chat_id, command, 0, 0).replace('🎲', ''))
    assert response in range(int(command.replace('д', ''))+1)


@pytest.mark.parametrize('chat_id, command', [(test_chat_id, 'фракция'), (test_chat_id, 'навык')])
def test_heroes_helper(chat_id, command):
    response = navigation.response_definition(chat_id, command, 0, 0).replace('🎲 ', '')
    assert response in herofractions or response in position


@pytest.mark.parametrize('chat_id, command, expect_response', [(test_chat_id, 'что такое банан', banan)])
def test_wiki(chat_id, command, expect_response):
    assert navigation.response_definition(chat_id, command, 0, 0) == expect_response
