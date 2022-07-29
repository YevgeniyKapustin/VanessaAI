import sys
sys.path.append("..")
from vk_api.bot_longpoll import VkBotEventType
from actions import remove_msg
from commands_logic.mute import Mute
from filtring import message_filtering
from navigation import response_definition
from vanessa.connection_to_vk.connection import longpoll
# from vanessa.vanessas_avatar.vanessa_look import VanessaAvatar
# from vanessa.settings import debug  # not needed on the server


class Vanessa(Mute):

    def __init__(self):
        super().__init__()

    def run(self):
        print('Server started')
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
    # if not debug:  # does not work on the server, my ip is needed
    #     VanessaAvatar().refresh_avatar()
    Vanessa().run()
