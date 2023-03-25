"""Module for interactive addition of commands by users."""
from sqlite3 import IntegrityError

from basic_actions.actions import send_text
from basic_actions.database import DataBase
from service_files.big_strings import commands_list_postfix


class Command(object):
    type = None
    strategy = None
    request = None
    response = None


class Commands(object):
    """Class for working with custom commands.

    :Methods:
    - get_commands()
    - add_command(event)
    - remove_command(event)
    """

    def __init__(self):
        self.db = DataBase()

    def get_commands(self) -> str:
        """Return all commands from db."""
        prefix = 'Команды на текущий момент:<br>Запрос, Ответ, Тип, Контекст'
        postfix = commands_list_postfix
        commands = ''

        for index, i in enumerate(self.db.get_all_commands_data()):
            commands += f'{index + 1}. {i[3]}: {i[2]}, {i[0]}, {i[1]}<br>'

        return f'{prefix}<br><br>{commands}<br><br>{postfix}'

    def add_command(self, event) -> str or None:
        """Add command to db."""
        text = event.msg.text
        chat_id = event.chat_id
        try:
            cmd = Command()
            command_data = self._define_command(text)
            cmd.request, cmd.response, cmd._type = command_data

            if self._define_prohibitions(cmd.request, chat_id):
                return None

            strategy = self._define_strategy(cmd.type)
            if strategy == 'contextual':
                cmd.type = cmd.type[:-1]

            attch = self._define_attachment(cmd.type, event)
            if attch:
                cmd.response = f'{cmd.type}{attch["owner_id"]}_{attch["id"]}'

            if cmd.request and cmd.response and cmd.type and strategy:
                try:
                    self.db.set_command(cmd)
                except IntegrityError:
                    self.db.update_command(cmd)
                self._success_add(chat_id, cmd)
            else:
                return self._something_wrong(chat_id)
        except (IndexError, ValueError):
            return self._something_wrong(chat_id)

    def remove_command(self, event) -> str:
        """Remove command from db.

        :param event: example: удалить команду текст запрос
        """
        msg = event.msg.text.split(':')
        request = msg[0].strip()
        chat_id = event.chat_id

        if request == 'сус':
            return send_text(chat_id, 'сус священен')
        if request:
            self.db.remove_command(request)
            return send_text(chat_id, f'команда {request} была удалена')
        else:
            return send_text(chat_id, 'чета ты насусил братик')

    def _define_command(self, text: str) -> tuple:
        """Extract data from a message.

        :param text: message sent by user
        """
        data: list = self._filtering(text)

        _type: str = self._get_command_type(data)
        data.remove(text[0])

        msg: list = ' '.join(text).split(':')

        request = msg[0]
        response = msg[1]

        return request, response, _type

    @staticmethod
    def _something_wrong(chat_id: int) -> str:
        """Send an error message.

        :param chat_id: id of the chat to which the message will be sent
        """
        return send_text(chat_id, 'чета ты насусил братик')

    @staticmethod
    def _get_command_type(data: list) -> str:
        """Return type from command data.

        :param data: command data
        """
        try:
            return data[0]
        except IndexError as error:
            return str(error)

    @staticmethod
    def _filtering(text: str) -> list:
        """Remove redundant information from the message.

        :param text: message sent by user
        """
        if not isinstance(text, list):
            text = text.lower().split(' ')
        text.remove('команду')
        if 'добавить' in text:
            text.remove('добавить')
        else:
            text.remove('удалить')
        return text

    @staticmethod
    def _define_strategy(_type: str) -> str:
        """Determine the command strategy.

        :param _type: raw command type
        """
        if _type[-1] == '_':
            return 'contextual'
        else:
            return 'normal'

    @staticmethod
    def _define_prohibitions(request: str, chat_id: int) -> str or None:
        """Determine the command strategy.

        :param request: request for a new command
        :param chat_id: id of the chat to which the message will be sent
        :return: string if found prohibitions else None
        """
        if request == 'сус':
            return send_text(chat_id, 'сус священен')
        elif 'добавить команду' in request:
            return send_text(chat_id, 'неа')
        elif 'удалить команду' in request:
            return send_text(chat_id, 'неа')
        return None

    @staticmethod
    def _define_attachment(_type: str, event):
        """Determine the command strategy.

        :param _type: command type
        :param event: object with information about the event
        """
        if _type == 'гиф':
            attch_type = 'doc'
        elif _type == 'изображение':
            attch_type = 'photo'
        else:
            return None

        attachment = event.attachments[0][f'{attch_type}']

        return attachment

    @staticmethod
    def _success_add(chat_id, cmd):
        return send_text(chat_id, f'команда {cmd.request} была добавлена')
