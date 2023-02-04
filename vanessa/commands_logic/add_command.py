"""Module for custom commands"""
from vanessa.actions import Actions
import json


class Commands:
    """Class for working with custom commands"""
    def __init__(self):
        self.send_text = Actions().send_text

    command_types = [
        'text_commands',
        'indirect_text_commands',
        'gif_commands',
        'indirect_gif_commands',
        'img_commands',
        'indirect_img_commands',
        'stick_commands'
    ]

    def get_commands(self):
        """Returns all commands written in commands.json"""
        with open('../commands.json', 'r') as f:
            commands = json.load(f)

        response = ''

        for i, command_type in enumerate(self.command_types):
            iterated_commands = commands[i][command_type]
            command = self._swap_command_type_en_to_ru(command_type)
            response += f'<br><br>{command}:<br><br>'

            for msg in iterated_commands:
                response += f'{msg}: {iterated_commands[msg]}<br>'

        response += '''<br><br>полезные команды:<br>
        фракция - генерирует случайную фракцию из героев 5
        д* - генерирует случайное число в диапазоне от 1 до указанного числа
        что такое* - отвечает первыми тремя предложениями из википедии
        мут* - удаляет все новые сообщения этого пользователя(только для админов)
        размут* - выключает мут для этого пользователя(только для админов)
        гитхаб/github - ссылка на этот репозиторий
        добавить команду помощь - показывает информацию о добавлении команд
        команды - показывает полный список команд'''

        return response

    def add_command(self, msg, chat_id, event):
        """Example: добавить команду текст_внутри вопрос: ответ"""
        try:
            index, command_type, msg = self._command_type_definition(msg,
                                                                     chat_id)
        except ValueError:
            return self.send_text(chat_id, 'чета ты насусил братик')
        if index == 'help':
            return ''
        msg = msg.split(':')
        try:
            request = msg[0].strip()
            if request == 'сус':
                return self.send_text(chat_id, 'сус священен')
            elif 'добавить команду' in request:
                return self.send_text(chat_id, 'неа')
            elif 'удалить команду' in request:
                return self.send_text(chat_id, 'неа')
            response = msg[1].strip()

            if command_type == 'gifs_commands' or command_type == \
                    'indirect_gifs_commands':
                attachment = event.message.attachments[0]['doc']
                response = f'doc{attachment["owner_id"]}_{attachment["id"]}'

            elif command_type == 'img_commands' or command_type == \
                    'indirect_img_commands':
                attachment = event.message.attachments[0]['photo']
                response = f'photo{attachment["owner_id"]}_{attachment["id"]}'

            if request and response and command_type:
                with open('../commands.json', 'r') as f:
                    commands = json.load(f)
                commands[index][command_type][request] = response

                with open('../commands.json', 'w') as f:
                    json.dump(commands, f, indent=4)
                return self.send_text(chat_id, f'команда {request} была '
                                               f'добавлена')
            else:
                return self.send_text(chat_id, 'чета ты насусил братик')
        except IndexError:
            return self.send_text(chat_id, 'чета ты насусил братик')

    def remove_command(self, msg, chat_id):
        """Example: удалить команду текст_внутри вопрос"""
        try:
            index, command_type, msg = self._command_type_definition(msg,
                                                                     chat_id)
        except ValueError:
            return self.send_text(chat_id, 'чета ты насусил братик')

        if index == 'help':
            return ''

        msg = msg.split(':')
        request = msg[0].strip()

        if request == 'сус':
            return self.send_text(chat_id, 'сус священен')

        if request and command_type:
            with open('../commands.json', 'r') as f:
                commands = json.load(f)
            try:
                commands[index][command_type].pop(request)
            except KeyError:
                return self.send_text(chat_id, 'чета ты насусил братик')
            with open('../commands.json', 'w') as f:
                json.dump(commands, f, indent=4)
            return self.send_text(chat_id, f'команда {request} была удалена')

        else:
            return self.send_text(chat_id, 'чета ты насусил братик')

    def _command_type_definition(self, msg, chat_id):
        if msg == 'добавить команду помощь':
            add_help = 'добавить команду (тип команды) (запрос): (ответ) \
                       например: добавить команду текст амогус: тутуту \
                       в случае ответа для гиф нужен его url, для стикера id \
                       типы команд: текст, гиф, изображение, стикер, ' \
                       'гиф_внутри, изображение_внутри'
            self.send_text(chat_id, add_help)

            return 'help', 'help', 'help'

        msg = msg.lower().split(' ')
        msg = self._filtring(msg)

        try:
            command_type = msg[0]
            msg.remove(msg[0])
        except IndexError:
            return ''

        if command_type == 'текст':
            index = 0
        elif command_type == 'текст_внутри':
            index = 1
        elif command_type == 'гиф':
            index = 2
        elif command_type == 'гиф_внутри':
            index = 3
        elif command_type == 'изображение':
            index = 4
        elif command_type == 'изображение_внутри':
            index = 5
        elif command_type == 'стикер':
            index = 6
        else:
            return ''

        return index, \
            self._swap_command_type_ru_to_en(command_type), ' '.join(msg)

    @staticmethod
    def _swap_command_type_en_to_ru(command_type):
        if command_type == 'text_commands':
            return 'текст'
        elif command_type == 'indirect_text_commands':
            return 'текст_внутри'
        elif command_type == 'gif_commands':
            return 'гиф'
        elif command_type == 'indirect_gif_commands':
            return 'гиф_внутри'
        elif command_type == 'img_commands':
            return 'изображение'
        elif command_type == 'indirect_img_commands':
            return 'изображение_внутри'
        elif command_type == 'stick_commands':
            return 'стикер'
        else:
            return f'"{command_type}" is not a command type'

    @staticmethod
    def _swap_command_type_ru_to_en(command_type):
        if command_type == 'текст':
            return 'text_commands'
        elif command_type == 'текст_внутри':
            return 'indirect_text_commands'
        elif command_type == 'гиф':
            return 'gif_commands'
        elif command_type == 'гиф_внутри':
            return 'indirect_gif_commands'
        elif command_type == 'изображение':
            return 'img_commands'
        elif command_type == 'изображение_внутри':
            return 'indirect_img_commands'
        elif command_type == 'стикер':
            return 'stick_commands'
        else:
            return f'"{command_type}" is not a command type'

    @staticmethod
    def _filtring(msg):
        msg.remove('команду')
        if 'добавить' in msg:
            msg.remove('добавить')
        else:
            msg.remove('удалить')
        return msg
