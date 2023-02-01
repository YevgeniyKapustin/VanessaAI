from vanessa.response import Response
from pytest import mark
from mock import patch

test_chat_id = 4
test_cases = [
    [(test_chat_id, 'мут', 'наш [id560930170|друг] пока что отдохнет')],
    [(test_chat_id, 'мут', 'я бы сказала, что это несколько возмутительно')],
    [(test_chat_id, 'мут', 'photo-212138773_457239033')],
]
members = {"items": [{"member_id": 465630601, "is_admin": True},
                     {"member_id": 560930170, "is_admin": False},
                     {"member_id": -212138773, "is_admin": True}]}


@mark.parametrize('chat_id, command, expect_response', test_cases[0])
def test_mute(chat_id, command, expect_response):
    with patch('vanessa.commands_logic.mute.Mute._Mute__members_search') as members_mock:
        members_mock.return_value = members
        with patch('vanessa.commands_logic.mute.Mute._Mute__victim_id_search') as victim_id_mock:
            victim_id_mock.return_value = '560930170'
            with patch('vanessa.commands_logic.mute.Mute._Mute__member_status_check') as from_check_mock:
                from_check_mock.return_value = True
                assert Response().response_definition(chat_id, command, 0, 0) == expect_response


@mark.parametrize('chat_id, command, expect_response', test_cases[1])
def test_mute_vanessa(chat_id, command, expect_response):
    with patch('vanessa.commands_logic.mute.Mute._Mute__members_search') as members_mock:
        members_mock.return_value = members
        with patch('vanessa.commands_logic.mute.Mute._Mute__victim_id_search') as victim_id_mock:
            victim_id_mock.return_value = '-212138773'
            with patch('vanessa.commands_logic.mute.Mute._Mute__member_status_check') as from_check_mock:
                from_check_mock.return_value = True
                assert Response().response_definition(chat_id, command, 0, 0) == expect_response


@mark.parametrize('chat_id, command, expect_response', test_cases[2])
def test_mute_admin(chat_id, command, expect_response):
    with patch('vanessa.commands_logic.mute.Mute._Mute__members_search') as members_mock:
        members_mock.return_value = members
        with patch('vanessa.commands_logic.mute.Mute._Mute__victim_id_search') as victim_id_mock:
            victim_id_mock.return_value = '465630601'
            with patch('vanessa.commands_logic.mute.Mute._Mute__member_status_check') as from_check_mock:
                from_check_mock.return_value = True
                assert Response().response_definition(chat_id, command, 0, 0) == expect_response


@mark.parametrize('chat_id, command, expect_response', test_cases[2])
def test_mute_from_not_admin(chat_id, command, expect_response):
    with patch('vanessa.commands_logic.mute.Mute._Mute__members_search') as members_mock:
        members_mock.return_value = members
        with patch('vanessa.commands_logic.mute.Mute._Mute__victim_id_search') as victim_id_mock:
            victim_id_mock.return_value = '560930170'
            with patch('vanessa.commands_logic.mute.Mute._Mute__member_status_check') as from_check_mock:
                from_check_mock.return_value = False
                assert Response().response_definition(chat_id, command, 0, 0) == expect_response
