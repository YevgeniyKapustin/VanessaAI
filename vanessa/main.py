"""The main module of the bot, containing the methods for launching it.

For questions, you can contact me at:
VK - https://vk.com/kapystageniy
TG - @kapustaevg
"""
from datetime import datetime
from os import path
from requests import ReadTimeout
from requests.exceptions import ProxyError

from vk_api.bot_longpoll import VkBotEventType

from basic_actions.actions import remove_msg
from commands_logic.mute import Mute
from basic_actions.response import Response
from prepare.connection import Connection


class Vanessa:
    """The main class for the bot that implements its main work cycle."""

    def __init__(self):
        self.__starting_counter = 0
        self.__issue_that_occurred = 'No issue occurred'

    def launch(self):
        """Start and reloading the bot in case of an exception.

        Also monitors data updates for logs and triggers logging.
        """
        while True:
            self.__starting_counter += 1

            self.__log_about_launch()
            self.__issue_that_occurred = 'No issue occurred'

            try:
                self.__run()
            except ReadTimeout:
                self.__issue_that_occurred = 'ReadTimeout'
            except ProxyError:
                self.__issue_that_occurred = 'ProxyError'

    def __log_about_launch(self):
        """Print launch information and writes to log.txt."""
        log = f'Server started # {self.__starting_counter} {datetime.now()} ' \
              f'issue: {self.__issue_that_occurred}'
        previous_logs = ''

        print(log)

        if path.isfile('service_files/log.txt'):
            with open('service_files/log.txt', 'r') as read_f:
                previous_logs = read_f.read()

        with open('service_files/log.txt', 'w') as write_f:
            write_f.write(f'{previous_logs}{log}\n')

    def __run(self):
        """Reacts to messages from conversations in which the bot is active.

        If the sender of the msg is muted, deletes his msg.
        Else it sends msg to the response definition for response_definition.
        """
        for event in Connection().longpoll.listen():
            response = Response()

            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg = event.object.message
                peer_id = msg['peer_id']

                if str(msg['from_id']) in Mute.get_shut_up_people_list():
                    remove_msg(peer_id, msg['conversation_message_id'])
                else:
                    chat_id = event.chat_id
                    msg = self.__message_filtering(msg['text'])
                    response.response_definition(chat_id, msg, peer_id, event)

    @staticmethod
    def __message_filtering(msg: str):
        """Filter the message and converts the message to lowercase."""
        filterable_text = {
            'ванесса'
            'ванесса,'
            '[club212138773|@vanessakapustovna]'
            '[club212138773|@vanessakapustovna],'
        }
        msg = msg.lower().split(' ')
        for word in msg:
            if word in filterable_text:
                msg.remove(word)
        return ' '.join(msg)


if __name__ == '__main__':
    Vanessa().launch()
