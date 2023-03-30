from mock.mock import patch

from commands_logic.add_command import Commands
from tests.test_actions import MockEvent


@patch('basic_actions.database.DataBase.set_command')
def test_add_command(mock_set_command):
    mock_set_command.return_value = True

    mock_event = MockEvent()
    mock_event.msg.text = 'добавить команду текст биба: и боба'

    assert Commands().add_command(mock_event) == 'команда биба была добавлена'


@patch('basic_actions.database.DataBase.remove_command')
def test_remove_command(mock_remove_command):
    mock_remove_command.return_value = True

    mock_event = MockEvent()
    mock_event.msg.text = 'удалить команду биба'

    assert Commands().remove_command(mock_event) == 'команда биба была удалена'


@patch('basic_actions.database.DataBase.get_all_commands_data')
def test_get_commands(mock_get_all_commands_data):
    mock_get_all_commands_data.return_value = (
        ('текст', 'normal', 'биба', 'боба'),)

    assert Commands().get_commands() == (
        'Команды на текущий момент:<br>Запрос, Ответ, Тип, Контекст<br><br>1. биба: '
        'боба, текст, normal<br><br><br>Прочие команды:<br>\n'
        '        фракция - генерирует случайную фракцию из героев 5\n'
        '        д* - генерирует случайное число в диапазоне от 1 до указанного '
        'числа\n'
        '        что такое* - отвечает первыми тремя предложениями из википедии\n'
        '        мут* - удаляет все новые сообщения этого пользователя(только для '
        'админов)\n'
        '        размут* - выключает мут для этого пользователя(только для админов)\n'
        '        добавить команду помощь - показывает информацию о добавлении команд\n'
        '        рарити - отправляет случайную рарити\n'
        '        абоба - абоба\n'
        '        команды - показывает полный список команд')
