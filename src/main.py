"""Модуль для основного класса бота."""
from loguru import logger
from vk_api.bot_longpoll import VkBotEventType

from src.services import vk
from src.utils.controller import Controller
from src.services.events import Event, extract_msg_from_event, Message


class Bot(object):
    """Главный класс Ванессы, ведет логи.

    Методы:
    launch -- запускает бота

    """
    def __init__(self):
        logger.add('.log')

    @logger.catch()
    def launch(self):
        """Запускает бота: прослушивает эвенты, отлавливает исключения."""
        while True:
            try:
                logger.info('launch...')
                self.__run()
            except Exception as exception:
                logger.critical(exception)

    @staticmethod
    def __run():
        for event in vk.get_longpoll().listen():
            logger.debug(f'catch {event}')
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                msg: Message = extract_msg_from_event(event)
                event = Event(msg, event.chat_id, event.message.attachments)

                Controller(event).recognition()
