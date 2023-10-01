from pydantic import BaseModel


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
    attachments: dict = None


class EventBuilder(object):
    """Provides methods for creating an event object.

    :Methods:
    get_event()

    set_msg()
    set_chat_id()
    set_attachment()
    """
    def __init__(self):
        self.__event = Event

    def get_event(self):
        return self.__event

    def set_msg(self, msg: object):
        self.__event.msg = msg
        return self

    def set_chat_id(self, chat_id: int):
        self.__event.chat_id = chat_id
        return self

    def set_attachment(self, event):
        self.__event.attachments = event.message.attachments
        return self
