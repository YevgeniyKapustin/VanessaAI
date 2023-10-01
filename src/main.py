from logger import logger
from requests import ReadTimeout
from requests.exceptions import ProxyError
from vk_api import ApiError
from vk_api.bot_longpoll import VkBotEventType

from src.utils import vk
from src.utils.controller import Controller
from src.utils.database import DataBase
from src.utils.events import Event, extract_msg_from_event, Msg


class Bot(object):
    def __init__(self):
        self.db = DataBase()

    def launch(self):
        while True:
            try:
                self.__run()
            except (ReadTimeout, ProxyError, ApiError) as exception:
                logger.critical(exception)

    @staticmethod
    def __run():
        for event in vk.get_longpoll().listen():

            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg: Msg = extract_msg_from_event(event)
                event = Event(msg, event.chat_id, event.message.attachments)

                Controller(event).definition()


if __name__ == '__main__':
    Bot().launch()
