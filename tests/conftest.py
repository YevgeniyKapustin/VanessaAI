from app.core.messages import StoredMessage


def make_message(msg_id: int, content: str = "test") -> StoredMessage:
    return StoredMessage(
        id=msg_id,
        role="user",
        content=content,
    )
