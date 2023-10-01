"""The main module of the bot, containing the methods for launching it.

For questions, you can contact me at:
VK - https://vk.com/kapystaevg
TG - https://t.me/kapustaevg03
"""
from datetime import datetime
from os import path

from requests import ReadTimeout
from requests.exceptions import ProxyError
from vk_api import ApiError
from vk_api.bot_longpoll import VkBotEventType

from src.utils.actions import remove_msg
from src.utils.database import DataBase
from src.utils import Msg, EventBuilder
from src.utils import Controller
from src.utils.connection import Connection


class Main(object):
    """Controls the processing of events and sends them to the business logic.

    :Methods:
    launch()
    """

    __instance = None

    def __new__(cls, *args, **kwargs):
        if not cls.__instance:
            cls.__instance = super(cls, cls).__new__(cls)
        return cls.__instance

    def __init__(self):
        self.__starting_counter = 0
        self.__exception = 'No exception occurred'
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
            except (ReadTimeout, ProxyError, ApiError) as exception:
                self.__exception = exception

    def __log_about_launch(self):
        """Print launch information and writes to log.txt."""
        log = f'Server started # {self.__starting_counter} {datetime.now()} ' \
              f'issue: {self.__exception}'
        previous_logs = ''

        print(log)

        if path.isfile('log.txt'):
            with open('log.txt', 'r') as read_f:
                previous_logs = read_f.read()

        with open('log.txt', 'w') as write_f:
            write_f.write(f'{previous_logs}{log}\n')

    def __run(self):
        """Reacts to messages from conversations in which the bot is active.

        If the sender of the msg is muted, deletes his msg.
        Else it sends msg to the response definition for response_definition.
        """
        for event in self.longpoll.listen():

            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg = Msg.parse_obj(event.object.message)
                msg.text = msg.text.lower()
                event = (
                    EventBuilder().set_msg(msg).set_chat_id(event.chat_id).
                    set_attachment(event).get_event()
                )

                if self.db.get_shut_up_person(event.msg.from_id):
                    remove_msg(event)
                else:
                    Controller(event).definition()


if __name__ == '__main__':
    Main().launch()
