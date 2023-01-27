from sys import path
path.append("..")
from requests import ReadTimeout
from requests.exceptions import ProxyError
from vk_api.bot_longpoll import VkBotEventType
from actions import remove_msg
from commands_logic.mute import Mute
from filtring import message_filtering
from navigation import Response
from vanessa.connection_to_vk.connection import longpoll


class Vanessa:

    starting_counter = 0

    def launch(self):
        self.starting_counter += 1
        try:
            self.run()
        except ReadTimeout:
            self.launch()
        except ProxyError:
            self.launch()

    def run(self):
        print(f'Server started № {self.starting_counter}')
        for event in longpoll.listen():
            response = Response()
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg = event.object.message
                peer_id = msg['peer_id']
                if str(msg['from_id']) in Mute.get_shut_up_people_list():
                    remove_msg(peer_id, msg['conversation_message_id'])
                else:
                    chat_id = event.chat_id
                    msg = message_filtering(msg['text'])
                    response.response_definition(chat_id, msg, peer_id, event)


if __name__ == '__main__':
    Vanessa().launch()
