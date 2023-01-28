from datetime import datetime
from requests import ReadTimeout
from requests.exceptions import ProxyError

from vk_api.bot_longpoll import VkBotEventType

from actions import remove_msg
from commands_logic.mute import Mute
from filtring import message_filtering
from navigation import Response
from vanessa.connection_to_vk.connection import longpoll


class Vanessa:
    """The main class for the bot that implements its main work cycle"""

    def __init__(self):
        self.starting_counter = 0
        self.issue_that_occurred = 'No issue occurred'

    def launch(self):
        """Start and restarts the __run in case of an error and causes
        __log_about_launch"""
        self.starting_counter += 1
        self.issue_that_occurred = 'No issue occurred'

        self.__log_about_launch()

        try:
            self.__run()
        except ReadTimeout:
            self.issue_that_occurred = 'ReadTimeout'
            self.launch()
        except ProxyError:
            self.issue_that_occurred = 'ProxyError'
            self.launch()

    def __log_about_launch(self):
        """Print launch information and writes to log.txt"""
        log = f'Server started # {self.starting_counter} {datetime.now()} ' \
              f'issue: {self.issue_that_occurred}'

        print(log)

        with open('log.txt', 'r') as read_f:
            previous_logs = read_f.read()
            with open('log.txt', 'w') as write_f:
                write_f.write(f'{previous_logs}{log}\n')

    @staticmethod
    def __run():
        """Reacts to messages from conversations in which the bot is active
        If the sender of the msg is muted, deletes his msg
        Else it sends msg to the response definition for response_definition
        """

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
