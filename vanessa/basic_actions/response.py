from commands_logic.cabbagesite import get_players_winrate, \
    get_fractions_winrate
from commands_logic.add_command import Commands
from commands_logic.mute import Mute
from commands_logic.randomize import send_random_fraction, \
    send_random_zmiysphrases, send_random_rarity, send_roll_dice
from commands_logic.wiki import send_wiki_article
from basic_actions.actions import send_text, send_stick, send_file
from basic_actions.database import DataBase


class Response:
    """The intermediary class between commands and responses."""
    def __init__(self, chat_id: int, msg: str, peer_id: int, event: object):
        self.chat_id = chat_id
        self.msg = msg
        self.peer_id = peer_id
        self.event = event
        self.db = DataBase()

    def definition(self):
        """Causes questions to be checked for an answer."""
        if not self.__check_special_commands():
            self.__check_db_commands()

    def __check_db_commands(self):

        data = self.db.get_response(self.msg)

        if data:
            return self.__send_choice()

        for i in self.db.get_all_contextual():
            if i in self.msg:
                return self.__send_choice()

    def __send_choice(self):
        response, _type = self.db.get_response(self.msg)

        if _type == 'текст':
            return send_text(self.chat_id, response)
        elif _type == 'гиф' or _type == 'изображение':
            return send_file(self.chat_id, response)
        elif _type == 'стикер':
            return send_stick(self.chat_id, response)

    def __check_special_commands(self):
        """Checking hard code commands."""
        if self.msg == 'команды':
            return send_text(self.chat_id, Commands().get_commands())

        elif self.msg == 'фракция':
            return send_random_fraction(self.chat_id)

        elif self.msg[:9] in ['что такое', 'кто такая', 'кто такой']:
            return send_wiki_article(self.chat_id, self.msg)

        elif self.msg[:3] == 'мут':
            return Mute().shut_up(self.chat_id, self.msg, self.peer_id,
                                  self.event)

        elif self.msg[:6] == 'размут':
            return Mute.redemption(
                Mute(), self.chat_id, self.msg,
                self.event, self.peer_id
            )

        elif self.msg[:16] == 'добавить команду':
            return Commands.add_command(
                Commands(),
                self.msg, self.chat_id,
                self.event
            )

        elif self.msg[:15] == 'удалить команду':
            return Commands.remove_command(
                Commands(),
                self.msg,
                self.chat_id
            )

        elif self.msg == 'абоба':
            return send_random_zmiysphrases(self.chat_id)

        elif self.msg == 'рарити':
            return send_random_rarity(self.chat_id)

        elif self.msg == 'статистика игроков':
            return send_text(self.chat_id, get_players_winrate())

        elif self.msg == 'статистика фракций':
            return send_text(self.chat_id, get_fractions_winrate())

        elif self.msg[:1] == 'д':
            return send_roll_dice(self.chat_id, self.msg)

        return None
