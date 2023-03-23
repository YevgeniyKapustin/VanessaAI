from sqlite3 import IntegrityError

from basic_actions.actions import send_text
from basic_actions.database import DataBase


class Commands(object):
    """Class for working with custom commands"""

    def __init__(self):
        self.db = DataBase()

    def get_commands(self):
        """Returns all commands from db"""
        prefix = 'Команды на текущий момент:<br>Запрос, Ответ, Тип, Контекст'
        postfix = f'''Прочие команды:<br>
        фракция - генерирует случайную фракцию из героев 5
        д* - генерирует случайное число в диапазоне от 1 до указанного числа
        что такое* - отвечает первыми тремя предложениями из википедии
        мут* - удаляет все новые сообщения этого пользователя(только для админов)
        размут* - выключает мут для этого пользователя(только для админов)
        добавить команду помощь - показывает информацию о добавлении команд
        рарити - отправляет случайную рарити
        абоба - абоба
        команды - показывает полный список команд'''
        commands = ''

        for index, i in enumerate(self.db.get_all_commands_data()):
            commands += f'{index + 1}. {i[3]}: {i[2]}, {i[0]}, {i[1]}<br>'

        return f'{prefix}<br><br>{commands}<br><br>{postfix}'

    def add_command(self, msg: str, chat_id, event):
        """Example: добавить команду текст_внутри вопрос: ответ"""
        try:
            request, response, _type = self.define_command(msg)
            strategy = 'contextual'

            if request == 'сус':
                return send_text(chat_id, 'сус священен')
            elif 'добавить команду' in request:
                return send_text(chat_id, 'неа')
            elif 'удалить команду' in request:
                return send_text(chat_id, 'неа')

            if _type[-1] == '_':
                _type = _type[:-1]
            else:
                strategy = 'normal'

            if _type == 'гиф':
                attachment = event.message.attachments[0]['doc']
                response = f'doc{attachment["owner_id"]}_{attachment["id"]}'
            elif _type == 'изображение':
                attachment = event.message.attachments[0]['photo']
                response = f'photo{attachment["owner_id"]}_{attachment["id"]}'

            if request and response and _type:
                try:
                    self.db.set_command(_type, strategy, request, response)
                except IntegrityError:
                    self.db.update_command(_type, strategy, request, response)
                return send_text(chat_id, f'команда {request} была добавлена')
            else:
                return self.__some_wrong(chat_id)
        except IndexError or ValueError:
            return self.__some_wrong(chat_id)

    @staticmethod
    def __some_wrong(chat_id):
        return send_text(chat_id, 'чета ты насусил братик')

    def define_command(self, msg):
        msg: list = self._filtering(msg.lower().split(' '))

        _type = self._get_command_type(msg)
        msg.remove(msg[0])

        msg: list = ' '.join(msg).split(':')

        request = msg[0]
        response = msg[1]

        return request, response, _type

    @staticmethod
    def _get_command_type(msg):
        try:
            return msg[0]
        except IndexError as error:
            return error

    def remove_command(self, msg, chat_id):
        """Example: удалить команду текст запрос"""

        msg = msg.split(':')
        request = msg[0].strip()

        if request == 'сус':
            return send_text(chat_id, 'сус священен')

        if request:
            self.db.remove_command(request)
            return send_text(chat_id, f'команда {request} была удалена')
        else:
            return send_text(chat_id, 'чета ты насусил братик')

    @staticmethod
    def _command_type_definition(msg, chat_id):
        if msg == 'добавить команду помощь':
            add_help = '''добавить команду (тип ответа)(_) (запрос): (ответ)
                       например: добавить команду текст_ амогус: тутуту
                       нижнее подчеркивание нужно добавить если вы хотите, 
                       чтобы команда писалась в случае если запрос содержится 
                       в сообщении, а не целиком его составляла в случае ответа
                       для гиф или изображения нужен его url, для стикера id 
                       типы команд: текст, гиф, изображение, стикер'''
            send_text(chat_id, add_help)
            return None
        try:
            _type = msg[0]
        except IndexError as error:
            return error

        return _type

    @staticmethod
    def _filtering(msg) -> list:
        if not isinstance(msg, list):
            msg = msg.lower().split(' ')
        msg.remove('команду')
        if 'добавить' in msg:
            msg.remove('добавить')
        else:
            msg.remove('удалить')
        return msg
