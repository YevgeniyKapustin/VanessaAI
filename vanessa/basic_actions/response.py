from basic_actions.database import DataBase
from commands_logic.cabbagesite import get_winrate
from commands_logic.add_command import Commands
from commands_logic.mute import Mute
from commands_logic.randomize import send_random_fraction, \
    send_random_zmiys_phrases, send_random_rarity, send_roll_dice
from commands_logic.wiki import send_wiki_article
from basic_actions.actions import send_text, send_stick, send_file
from service_files.big_strings import commands_add_help


class Response(object):
    """The intermediary class between commands and responses."""
    def __init__(self, msg, event):
        self.chat_id = event.chat_id
        self.text = msg.text
        self.peer_id = msg.peer_id
        self.event = event
        self.msg = msg
        self.db = DataBase()
        self.add_help = commands_add_help

    def definition(self):
        """Causes questions to be checked for an answer."""
        if not self.__check_special_commands():
            self.__check_db_commands()

    def __check_db_commands(self):
        data = self.db.get_response_and_type(self.text)
        if data:
            return self.__send_choice(data[0], data[1])

        for data in self.db.get_all_commands():
            if data[0] in self.text:
                return self.__send_choice(data[2], data[1])

    def __send_choice(self, response, _type):
        if _type == 'текст':
            return send_text(self.chat_id, response)
        elif _type == 'гиф' or _type == 'изображение':
            return send_file(self.chat_id, response)
        elif _type == 'стикер':
            return send_stick(self.chat_id, response)

    def __check_special_commands(self):
        """Checking hard code commands."""
        if self.text == 'команды':
            return send_text(self.chat_id, Commands().get_commands())

        elif self.text == 'фракция':
            return send_random_fraction(self.chat_id)

        elif self.text[:9] in ['что такое', 'кто такая', 'кто такой']:
            return send_wiki_article(self.chat_id, self.text)

        elif self.text[:3] == 'мут':
            return Mute(self.msg, self.event).shut_up()

        elif self.text[:6] == 'размут':
            return Mute.redemption(
                Mute(self.msg, self.event))

        elif self.text == 'добавить команду помощь':
            return send_text(self.chat_id, self.add_help)

        elif self.text[:16] == 'добавить команду':
            return Commands.add_command(Commands(), self.text, self.event)

        elif self.text[:15] == 'удалить команду':
            return Commands.remove_command(Commands(), self.text, self.chat_id)

        elif self.text == 'абоба':
            return send_random_zmiys_phrases(self.chat_id)

        elif self.db.get_all_shut_up_person() and self.text == 'зверинец':
            return send_text(self.chat_id, self.db.get_all_shut_up_person())

        elif self.text == 'рарити':
            return send_random_rarity(self.chat_id)

        elif self.text == 'статистика игроков':
            return send_text(self.chat_id, get_winrate('players'))

        elif self.text == 'статистика фракций':
            return send_text(self.chat_id, get_winrate('fractions'))

        elif self.text[:1] == 'д':
            return send_roll_dice(self.chat_id, self.text)

        return None
