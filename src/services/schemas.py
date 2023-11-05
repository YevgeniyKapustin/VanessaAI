"""Pydantic объекты."""
from pydantic import BaseModel, AfterValidator
from typing_extensions import Annotated

from src.utils.validators import check_type, check_mention


class Message(BaseModel):
    """Объект для сообщений."""
    peer_id: int
    from_id: int
    conversation_message_id: int
    text: str
    reply_message: dict = None


class Command(BaseModel):
    """Объект для команд."""
    type: Annotated[str, AfterValidator(check_type)]
    request: Annotated[str, AfterValidator(check_mention)]
    response: Annotated[str, AfterValidator(check_mention)]
