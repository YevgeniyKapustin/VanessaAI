import json
from commands_logic.cabbagesite import Cabbagesite
from vanessa.actions import *
from vanessa.commands_logic import randomize as rnd, mute, add_command
from vanessa.commands_logic.wiki import send_wiki_article


class Response:

    def __init__(self):
        with open('commands.json', 'r') as f:
            self.commands = json.load(f)
        self.text_commands = self.commands[0]['text_commands']
        self.gifs_commands = self.commands[1]['gifs_commands']
        self.indirect_gifs_command = self.commands[2]['indirect_gifs_command']
        self.img_commands = self.commands[3]['img_commands']
        self.indirect_img_commands = self.commands[4]['indirect_img_commands']
        self.stick_commands = self.commands[5]['stick_commands']

    def response_definition(self, chat_id: int, msg: str, peer_id: int, event):
        """check for command detection"""

        for i in self.indirect_gifs_command:
            if i in msg:
                return send_file(chat_id, self.indirect_gifs_command[i])

        for i in self.indirect_img_commands:
            if i in msg:
                return send_file(chat_id, self.indirect_img_commands[i])

        if msg in self.text_commands:
            return send_text(chat_id, self.text_commands[msg])

        elif msg in self.gifs_commands:
            return send_file(chat_id, self.gifs_commands[msg])

        elif msg in self.img_commands:
            return send_file(chat_id, self.img_commands[msg])

        elif msg in self.stick_commands:
            return send_stick(chat_id, self.stick_commands[msg])
        # helpfull_commands
        elif msg == 'фракция':
            return rnd.send_random_fraction(chat_id)

        elif msg == 'навык':
            return send_text(chat_id, rnd.send_random_skill_position(chat_id))

        elif msg[:9] in ['что такое', 'кто такая', 'кто такой']:
            return send_wiki_article(chat_id, msg)

        elif msg[:3] == 'мут':
            return mute.Mute.shut_up(mute.Mute(), chat_id, msg, peer_id, event)

        elif msg[:6] == 'размут':
            return mute.Mute.redemption(mute.Mute(), chat_id, msg, event, peer_id)

        elif msg[:16] == 'добавить команду':
            return add_command.Commands.add_command(add_command.Commands(), msg, chat_id, event)

        elif msg[:15] == 'удалить команду':
            return add_command.Commands.remove_command(add_command.Commands(), msg, chat_id)

        elif msg == 'абоба':
            return rnd.send_random_zmiysphrases(chat_id)

        elif msg == 'статистика игроков':
            return send_text(chat_id, Cabbagesite.get_players_winrate())

        elif msg == 'статистика фракций':
            return send_text(chat_id, Cabbagesite.get_fractions_winrate())

        elif msg[:1] == 'д':
            return rnd.send_roll_dice(chat_id, msg)

        # end helpfull_commands
        else:
            for i in self.indirect_gifs_command:
                if i in msg:
                    return send_file(chat_id, self.indirect_gifs_command[i])

            for i in self.indirect_img_commands:
                if i in msg:
                    return send_file(chat_id, self.indirect_img_commands[i])
