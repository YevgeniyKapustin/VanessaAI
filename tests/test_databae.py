from dataclasses import dataclass

from basic_actions.database import DataBase


@dataclass
class Command(object):
    type: str = 'текст'
    strategy: str = 'normal'
    request: str = 'биба'
    response: str = 'и боба'


cmd = Command()
user_id = 1111


def test_set_command():
    assert DataBase.set_command(cmd)


def test_update_command():
    assert DataBase.update_command(cmd)


def test_get_response_and_type():
    assert DataBase.get_response_and_type(cmd.request) == ('и боба', 'текст')


def test_get_all_commands_for_strategy():
    assert DataBase.get_all_commands_for_strategy(cmd.strategy) == \
           [('биба', 'текст', 'и боба')]


def test_get_all_commands_data():
    assert DataBase.get_all_commands_data() == \
           [('текст', 'normal', 'биба', 'и боба')]


def test_remove_command():
    assert DataBase.remove_command(cmd.request)


def test_set_shut_up_person():
    assert DataBase.set_shut_up_person(user_id)


def test_get_all_shut_up_person():
    assert DataBase.get_all_shut_up_person() == [(1111,)]


def test_remove_from_shut_up_people():
    assert DataBase.remove_from_shut_up_people(user_id)
