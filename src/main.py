from logger import logger
from requests import ReadTimeout
from requests.exceptions import ProxyError
from vk_api import ApiError
from vk_api.bot_longpoll import VkBotEventType

from src.services import vk
from src.utils.controller import Controller
from src.services.events import Event, extract_msg_from_event, Message


class Bot(object):

    def launch(self):
        while True:
            try:
                logger.info('launch...')
                self.__run()
            except (ReadTimeout, ProxyError, ApiError) as exception:
                logger.critical(exception)

    @staticmethod
    def __run():
        for event in vk.get_longpoll().listen():
            logger.info(f'catch {event}')
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg: Message = extract_msg_from_event(event)
                event = Event(msg, event.chat_id, event.message.attachments)

                Controller(event).recognition()
