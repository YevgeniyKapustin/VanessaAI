from pydantic import BaseModel
from vk_api.bot_longpoll import VkBotMessageEvent

from src.utils import vk


class Message(BaseModel):
    """Message object."""
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Event(object):
    """Event object."""
    message: Message
    chat_id: int
    attachments: dict

    def __init__(self, message, chat_id, attachments=None):
        self.message = message
        self.chat_id = chat_id
        self.attachments = attachments

    def answer(self, text):
        vk.get_bot_api().messages.send(chat_id=self.chat_id, message=text, random_id=0)


def extract_msg_from_event(event: VkBotMessageEvent) -> Message:
    msg = Message.model_validate(event.object.message)
    msg.text = msg.text.lower()
    return msg
