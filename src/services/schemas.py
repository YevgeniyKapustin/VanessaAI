"""Pydantic объекты."""
from pydantic import BaseModel


class Message(BaseModel):
    """Объект для сообщений."""
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Command(BaseModel):
    """Объект для команд."""
    type: str
    request: str
    response: str
