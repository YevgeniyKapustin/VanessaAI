"""Contains the Response class, which selects a response to requests"""
import json
from os import path

from commands_logic.cabbagesite import get_players_winrate, \
    get_fractions_winrate
from commands_logic.add_command import Commands
from commands_logic.mute import Mute
from commands_logic.randomize import send_random_fraction, \
    send_random_zmiysphrases, send_random_rarity, send_roll_dice
from commands_logic.wiki import send_wiki_article
from basic_actions.actions import send_text, send_stick, send_file


class Response:
    """The intermediary class between commands and responses"""
    def __init__(self):
        self.chat_id = None
        self.msg = None
        self.peer_id = None
        self.event = None

        if not path.isfile('./service_files/commands.json'):
            default_json = [
                {"text_commands": {}},
                {"indirect_text_commands": {}},
                {"gif_commands": {}},
                {"indirect_gif_commands": {}},
                {"img_commands": {}},
                {"indirect_img_commands": {}},
                {"stick_commands": {}}
            ]
            with open('./service_files/commands.json', 'w') as f:
                json.dump(default_json, f, indent=4)

        with open('./service_files/commands.json', 'r') as f:
            self.commands = json.load(f)

        self.text_commands = self.commands[0]['text_commands']
        self.indirect_text_commands = \
            self.commands[1]['indirect_text_commands']
        self.gif_commands = self.commands[2]['gif_commands']
        self.indirect_gif_commands = self.commands[3]['indirect_gif_commands']
        self.img_commands = self.commands[4]['img_commands']
        self.indirect_img_commands = self.commands[5]['indirect_img_commands']
        self.stick_commands = self.commands[6]['stick_commands']

    def response_definition(self, chat_id: int, msg: str, peer_id: int, event):
        """Causes questions to be checked for an answer"""
        self.chat_id = chat_id
        self.msg = msg
        self.peer_id = peer_id
        self.event = event

        self.__check_special_commands()
        self.__check_json_commands()

    def __check_json_commands(self):
        """Checking commands written in commands.json"""
        if self.msg in self.text_commands:
            return send_text(self.chat_id, self.text_commands[self.msg])

        elif self.msg in self.gif_commands:
            return send_file(self.chat_id, self.gif_commands[self.msg])

        elif self.msg in self.img_commands:
            return send_file(self.chat_id, self.img_commands[self.msg])

        elif self.msg in self.stick_commands:
            return send_stick(self.chat_id, self.stick_commands[self.msg])

        for i in self.indirect_text_commands:
            if i in self.msg:
                return send_text(self.chat_id, self.indirect_text_commands[i])

        for i in self.indirect_gif_commands:
            if i in self.msg:
                return send_file(self.chat_id, self.indirect_gif_commands[i])

        for i in self.indirect_img_commands:
            if i in self.msg:
                return send_file(self.chat_id, self.indirect_img_commands[i])

    def __check_special_commands(self):
        """Checking hard code commands"""
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
