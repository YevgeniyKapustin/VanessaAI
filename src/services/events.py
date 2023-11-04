"""Модуль для работы с ивентами."""
from loguru import logger
from vk_api.bot_longpoll import VkBotMessageEvent
from vk_api.vk_api import VkApiMethod

from src.services.schemas import Message
from src.services import vk


class Event(object):
    """Объект для работы с ивентами и ответа на них."""
    __slots__ = ('message', 'chat_id', 'attachments', 'api')

    def __init__(
            self,
            message: Message,
            chat_id: int,
            attachments: dict | None = None
    ):
        self.message: Message = message
        self.chat_id: int = chat_id
        self.attachments: dict | None = attachments
        self.api: VkApiMethod = vk.get_bot_api()

    def text_answer(self, text: str) -> None:
        """Отвечает на ивент текстом.

        Аргументы:
        text -- текст для ответа

        """
        logger.info(f'text answer: {text}')
        self.api.messages.send(
            chat_id=self.chat_id,
            message=text,
            random_id=0
        )

    def gif_answer(self, url: str) -> None:
        """Отвечает на ивент гифкой.

        Аргументы:
        url -- URI гифки на серверах ВК

        """
        logger.info(f'url answer: {url}')
        self.api.messages.send(
            chat_id=self.chat_id,
            attachment=url,
            random_id=0
        )


def extract_msg_from_event(event: VkBotMessageEvent) -> Message:
    """Возвращает объект Message создавая его из VkBotMessageEvent.

    Аргументы:
    event -- VkBotMessageEvent

    """
    message = Message.model_validate(event.object.message)
    message.text = message.text.lower()
    return message
