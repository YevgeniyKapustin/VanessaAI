from pydantic import BaseModel


class Message(BaseModel):
    """Message object."""
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Command(BaseModel):
    type: str
    request: str
    response: str
