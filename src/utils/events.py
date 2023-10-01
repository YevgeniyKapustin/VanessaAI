from pydantic import BaseModel
from vk_api.bot_longpoll import VkBotMessageEvent


class Msg(BaseModel):
    """Message object."""
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Event(object):
    """Event object."""
    msg: Msg
    chat_id: int
    attachments: dict

    def __init__(self, msg, chat_id, attachments=None):
        self.msg = msg
        self.chat_id = chat_id
        self.attachments = attachments


def convert_json_event_to_msg_object(event: VkBotMessageEvent) -> Msg:
    msg = Msg.model_validate(event.object.message)
    msg.text = msg.text.lower()
    return msg
