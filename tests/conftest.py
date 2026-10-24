from vanessa.core.messages import StoredMessage

pytest_plugins = ["tests.trace_helpers"]


def make_message(msg_id: int, content: str = "test") -> StoredMessage:
    return StoredMessage(
        id=msg_id,
        role="user",
        content=content,
    )
