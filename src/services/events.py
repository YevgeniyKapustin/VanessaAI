from vk_api.bot_longpoll import VkBotMessageEvent
from vk_api.vk_api import VkApiMethod

from src.services.schemas import Message
from src.utils import vk


class Event(object):
    """Event object."""
    message: Message
    chat_id: int
    attachments: dict
    api: VkApiMethod

    def __init__(self, message, chat_id, attachments=None):
        self.message = message
        self.chat_id = chat_id
        self.attachments = attachments
        self.api = vk.get_bot_api()

    def text_answer(self, text: str):
        self.api.messages.send(
            chat_id=self.chat_id,
            message=text,
            random_id=0
        )

    def gif_answer(self, url: str):
        self.api.messages.send(
            chat_id=self.chat_id,
            attachment=url,
            random_id=0
        )


def extract_msg_from_event(event: VkBotMessageEvent) -> Message:
    message = Message.model_validate(event.object.message)
    message.text = message.text.lower()
    return message
