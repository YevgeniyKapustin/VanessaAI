import json
from actions import send_text


class Commands:

    def add_command(self, msg, chat_id, event):
        """Example: добавить команду текст_внутри вопрос: ответ"""
        try:
            index, command_type, msg = self.command_type_definition(msg, chat_id)
        except ValueError:
            return send_text(chat_id, 'чета ты насусил братик')
        if index == 'help':
            return ''
        msg = msg.split(':')
        try:
            request = msg[0].strip()
            if request == 'сус':
                return send_text(chat_id, 'сус священен')
            elif 'добавить команду' in request:
                return send_text(chat_id, 'неа')
            elif 'удалить команду' in request:
                return send_text(chat_id, 'неа')
            response = msg[1].strip()
            if command_type == 'gifs_commands' or command_type == 'indirect_gifs_commands':
                attachment = event.message.attachments[0]['doc']
                response = f'doc{attachment["owner_id"]}_{attachment["id"]}'
            elif command_type == 'img_commands' or command_type == 'indirect_img_commands':
                attachment = event.message.attachments[0]['photo']
                response = f'photo{attachment["owner_id"]}_{attachment["id"]}'
            if request and response and command_type:
                with open('commands.json', 'r') as f:
                    commands = json.load(f)
                commands[index][command_type][request] = response
                with open('commands.json', 'w') as f:
                    json.dump(commands, f, indent=4)
                return send_text(chat_id, f'команда {request} была добавлена')
            else:
                return send_text(chat_id, 'чета ты насусил братик')
        except IndexError:
            return send_text(chat_id, 'чета ты насусил братик')

    def remove_command(self, msg, chat_id):
        """Example: удалить команду текс_внутри вопрос"""
        try:
            index, command_type, msg = self.command_type_definition(msg, chat_id)
        except ValueError:
            return send_text(chat_id, 'чета ты насусил братик')
        if index == 'help':
            return ''
        msg = msg.split(':')
        request = msg[0].strip()
        if request == 'сус':
            return send_text(chat_id, 'сус священен')
        if request and command_type:
            with open('commands.json', 'r') as f:
                commands = json.load(f)
            try:
                commands[index][command_type].pop(request)
            except KeyError:
                return send_text(chat_id, 'чета ты насусил братик')
            with open('commands.json', 'w') as f:
                json.dump(commands, f, indent=4)
            return send_text(chat_id, f'команда {request} была удалена')
        else:
            return send_text(chat_id, 'чета ты насусил братик')

    def command_type_definition(self, msg, chat_id):
        if msg == 'добавить команду помощь':
            add_help = '''добавить команду (тип команды) (запрос): (ответ)
                       например: добавить команду текст амогус: тутуту
                       в случае ответа для гиф нужен его url, для стикера id
                       типы команд: текст, гиф, изображение, стикер, гиф_внутри, изображение_внутри'''
            send_text(chat_id, add_help)
            return 'help', 'help', 'help'
        msg = msg.lower().split(' ')
        msg = self.filtring(msg)
        try:
            command_type = msg[0]
            msg.remove(msg[0])
        except IndexError:
            return ''
        if command_type == 'текст':
            command_type = 'text_commands'
            index = 0
        elif command_type == 'гиф':
            command_type = 'gifs_commands'
            index = 1
        elif command_type == 'гиф_внутри':
            command_type = 'indirect_gifs_command'
            index = 2
        elif command_type == 'изображение':
            command_type = 'img_commands'
            index = 3
        elif command_type == 'изображение_внутри':
            command_type = 'indirect_img_commands'
            index = 4
        elif command_type == 'стикер':
            command_type = 'stick_commands'
            index = 5
        else:
            return ''
        return index, command_type, ' '.join(msg)

    @staticmethod
    def filtring(msg):
        msg.remove('команду')
        if 'добавить' in msg:
            msg.remove('добавить')
        else:
            msg.remove('удалить')
        return msg
