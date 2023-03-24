"""The main module of the bot, containing the methods for launching it.

For questions, you can contact me at:
VK - https://vk.com/kapystaevg
TG - @kapustaevg03
"""
from datetime import datetime
from os import path

from pydantic import BaseModel
from requests import ReadTimeout
from requests.exceptions import ProxyError
from vk_api.bot_longpoll import VkBotEventType

from basic_actions.actions import remove_msg
from basic_actions.database import DataBase
from basic_actions.response import Response
from prepare.connection import Connection


class Msg(BaseModel):
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Vanessa:
    """The main class for the bot that implements its main work cycle."""

    def __init__(self):
        self.__starting_counter = 0
        self.__exception = 'No issue occurred'
        self.db = DataBase()
        self.longpoll = Connection().longpoll

    def launch(self):
        """Start and reloading the bot in case of an exception.

        Also monitors data updates for logs and triggers logging.
        """
        while True:
            self.__starting_counter += 1

            self.__log_about_launch()
            self.__exception = 'No exception occurred'

            try:
                self.__run()
            except ReadTimeout as exception:
                self.__exception = exception
            except ProxyError as exception:
                self.__exception = exception

    def __log_about_launch(self):
        """Print launch information and writes to log.txt."""
        log = f'Server started # {self.__starting_counter} {datetime.now()} ' \
              f'issue: {self.__exception}'
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
        for event in self.longpoll.listen():

            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg = Msg.parse_obj(event.object.message)
                peer_id = msg.peer_id

                if self.db.get_shut_up_person(msg.from_id):
                    remove_msg(peer_id, msg.conversation_message_id)
                else:
                    Response(msg, event).definition()


if __name__ == '__main__':
    Vanessa().launch()
