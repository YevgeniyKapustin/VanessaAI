from vk_api.bot_longpoll import VkBotEventType
from vanessa.actions import send_text, remove_msg
from vanessa.commands_logic.mute import Mute
from vanessa.filtring import message_filtering
from vanessa.navigation import response_definition
from vanessa.connection import longpoll
from pickle import dump, load


class Vanessa(Mute):

    def __init__(self):
        super().__init__()
        try:
            with open('serial_number.data', 'rb') as f:
                self.serial_number = load(f)
        except FileNotFoundError:
            self.serial_number = 0
        with open('serial_number.data', 'wb') as f:
            self.serial_number += 1
            dump(self.serial_number, f)
        self.version = 'VanessaV2R'

    def run(self):
        print("Server started")
        send_text(4, f'Здравствуйте, меня зовут Ванесса. А если быть точной {self.version}экземпляр{self.serial_number}')
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                peer_id = event.object.message['peer_id']
                if str(event.object.message['from_id']) in self.shut_up_people:
                    remove_msg(peer_id, event.object.message['conversation_message_id'])
                else:
                    chat_id = event.chat_id
                    msg = message_filtering(event.object.message['text'])
                    response_definition(chat_id, msg, peer_id, event)


if __name__ == '__main__':
    Vanessa().run()
