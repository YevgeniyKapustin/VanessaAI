"""Module for interactive addition of commands by users."""
from sqlite3 import IntegrityError

from basic_actions.actions import send_text
from basic_actions.database import DataBase
from service_files.big_strings import commands_list_postfix


class Commands(object):
    """Class for working with custom commands.

    :Methods:
    - get_commands()
    - add_command(msg, event)
    - remove_command(msg, chat_id)
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

    def add_command(self, msg: str, event) -> str or None:
        """Add command to db.

        :param msg: example: "добавить команду текст_ запрос: ответ"
        :param event: object with information about the event
        """
        chat_id = event.chat_id
        try:
            request, response, _type = self._define_command(msg)

            if self._define_prohibitions(request, chat_id):
                return None

            strategy = self._define_strategy(_type)
            if strategy == 'contextual':
                _type = _type[:-1]

            attch = self._define_attachment(_type, event)
            if attch:
                response = f'{_type}{attch["owner_id"]}_{attch["id"]}'

            if request and response and _type and strategy:
                try:
                    self.db.set_command(_type, strategy, request, response)
                except IntegrityError:
                    self.db.update_command(_type, strategy, request, response)
                return send_text(chat_id, f'команда {request} была добавлена')
            else:
                return self._something_wrong(chat_id)
        except (IndexError, ValueError):
            return self._something_wrong(chat_id)

    def remove_command(self, msg: str, chat_id: id) -> str:
        """Remove command from db.

        :param msg: example: удалить команду текст запрос
        :param chat_id: id of the chat to which the message will be sent
        """
        msg = msg.split(':')
        request = msg[0].strip()

        if request == 'сус':
            return send_text(chat_id, 'сус священен')
        if request:
            self.db.remove_command(request)
            return send_text(chat_id, f'команда {request} была удалена')
        else:
            return send_text(chat_id, 'чета ты насусил братик')

    def _define_command(self, msg: str) -> tuple:
        """Extract data from a message.

        :param msg: message sent by user
        """
        data: list = self._filtering(msg)

        _type: str = self._get_command_type(data)
        data.remove(msg[0])

        msg: list = ' '.join(msg).split(':')

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
    def _filtering(msg: str) -> list:
        """Remove redundant information from the message.

        :param msg: message sent by user
        """
        if not isinstance(msg, list):
            msg = msg.lower().split(' ')
        msg.remove('команду')
        if 'добавить' in msg:
            msg.remove('добавить')
        else:
            msg.remove('удалить')
        return msg

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

        attachment = event.message.attachments[0][f'{attch_type}']

        return attachment
