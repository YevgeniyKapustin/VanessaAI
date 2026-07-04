from dataclasses import dataclass

from app.core.messages import ContextMessage, stored_to_context
from app.core.protocols import MessageRepositoryProtocol
from app.core.session_trim import seconds_since_last_role, trim_session_by_idle_gap
from app.decision.reply_expectation import is_dismissal_request


@dataclass(frozen=True, slots=True)
class ChatSessionState:
    messages: list[ContextMessage]
    in_listen_window: bool
    idle_since_last_bot_seconds: float | None
    idle_expired: bool
    has_recent_dismissal: bool

    @property
    def recent_messages(self) -> list[ContextMessage]:
        return self.messages


def in_post_reply_listen_window(
    recent_messages: list[ContextMessage],
    *,
    max_messages: int,
    max_idle_seconds: float = 0,
) -> bool:
    if max_messages <= 0 or not recent_messages:
        return False
    if max_idle_seconds > 0:
        idle = seconds_since_last_role(recent_messages, "assistant")
        if idle is not None and idle > max_idle_seconds:
            return False
    user_count = 0
    for message in reversed(recent_messages):
        if message.role == "assistant":
            return 0 < user_count <= max_messages
        if message.role == "user":
            if is_dismissal_request(message.content):
                return False
            user_count += 1
    return False


def build_chat_session_state(
    messages: list[ContextMessage],
    *,
    max_idle_seconds: float,
    listen_max_messages: int,
) -> ChatSessionState:
    trimmed = trim_session_by_idle_gap(
        messages,
        max_idle_seconds=max_idle_seconds,
    )
    idle = seconds_since_last_role(trimmed, "assistant")
    idle_expired = (
        idle is not None
        and max_idle_seconds > 0
        and idle > max_idle_seconds
    )
    in_listen = in_post_reply_listen_window(
        trimmed,
        max_messages=listen_max_messages,
        max_idle_seconds=max_idle_seconds,
    )
    has_dismissal = any(
        message.role == "user" and is_dismissal_request(message.content)
        for message in trimmed
    )
    return ChatSessionState(
        messages=trimmed,
        in_listen_window=in_listen,
        idle_since_last_bot_seconds=idle,
        idle_expired=idle_expired,
        has_recent_dismissal=has_dismissal,
    )


async def load_chat_session_state(
    messages_repo: MessageRepositoryProtocol,
    *,
    window_size: int,
    max_idle_seconds: float,
    listen_max_messages: int,
) -> ChatSessionState:
    raw = [
        stored_to_context(message)
        for message in await messages_repo.get_recent(limit=window_size)
    ]
    return build_chat_session_state(
        raw,
        max_idle_seconds=max_idle_seconds,
        listen_max_messages=listen_max_messages,
    )
