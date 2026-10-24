from dataclasses import dataclass, field

from vanessa.core.messages import ContextMessage, stored_to_context
from vanessa.core.protocols import MessageRepositoryProtocol
from vanessa.core.session.dismissal import is_dismissal_request
from vanessa.core.session.session_trim import (
    earlier_tail,
    seconds_since_last_role,
    trim_session_by_idle_gap,
)


@dataclass(frozen=True, slots=True)
class EarlierWindow:
    """How much of the thread before the idle gap the prompt still sees."""

    count: int = 0
    max_age_seconds: float = 0


@dataclass(frozen=True, slots=True)
class ChatSessionState:
    messages: list[ContextMessage]
    in_listen_window: bool
    idle_since_last_bot_seconds: float | None
    idle_expired: bool
    has_recent_dismissal: bool
    # Tail of the older thread cut off by the idle gap (prompt context only:
    # gate rules and the listen window use ``messages``).
    earlier_messages: list[ContextMessage] = field(default_factory=list)

    @property
    def recent_messages(self) -> list[ContextMessage]:
        return self.messages

    @property
    def prompt_messages(self) -> list[ContextMessage]:
        """Earlier thread + recent session, for the planner prompt."""
        return [*self.earlier_messages, *self.messages]


def _listen_idle_blocks(
    recent_messages: list[ContextMessage],
    max_idle_seconds: float,
) -> bool:
    if max_idle_seconds <= 0:
        return False
    idle = seconds_since_last_role(recent_messages, "assistant")
    if idle is None:
        return False
    return idle > max_idle_seconds


def _listen_preconditions(
    recent_messages: list[ContextMessage],
    *,
    max_messages: int,
    max_idle_seconds: float,
) -> bool:
    if max_messages <= 0:
        return False
    if not recent_messages:
        return False
    return not _listen_idle_blocks(recent_messages, max_idle_seconds)


def _listen_user_tally(message: ContextMessage, user_count: int) -> int | None:
    if message.role != "user":
        return user_count
    if is_dismissal_request(message.content):
        return None
    return user_count + 1


def _users_since_last_assistant(
    recent_messages: list[ContextMessage],
) -> int | None:
    user_count = 0
    for message in reversed(recent_messages):
        if message.role == "assistant":
            return user_count
        user_count = _listen_user_tally(message, user_count)
        if user_count is None:
            return None
    return None


def in_post_reply_listen_window(
    recent_messages: list[ContextMessage],
    *,
    max_messages: int,
    max_idle_seconds: float = 0,
) -> bool:
    if not _listen_preconditions(
        recent_messages,
        max_messages=max_messages,
        max_idle_seconds=max_idle_seconds,
    ):
        return False
    user_count = _users_since_last_assistant(recent_messages)
    if user_count is None:
        return False
    return 0 < user_count <= max_messages


def build_chat_session_state(
    messages: list[ContextMessage],
    *,
    max_idle_seconds: float,
    listen_max_messages: int,
    earlier: EarlierWindow | None = None,
) -> ChatSessionState:
    trimmed = trim_session_by_idle_gap(
        messages,
        max_idle_seconds=max_idle_seconds,
    )
    window = earlier or EarlierWindow()
    earlier_messages = earlier_tail(
        messages,
        trimmed,
        count=window.count,
        max_age_seconds=window.max_age_seconds,
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
        earlier_messages=earlier_messages,
    )


async def load_chat_session_state(
    messages_repo: MessageRepositoryProtocol,
    *,
    window_size: int,
    max_idle_seconds: float,
    listen_max_messages: int,
    channel: str = "telegram",
    earlier: EarlierWindow | None = None,
) -> ChatSessionState:
    raw = [
        stored_to_context(message)
        for message in await messages_repo.get_recent(
            limit=window_size,
            channel=channel,
        )
    ]
    return build_chat_session_state(
        raw,
        max_idle_seconds=max_idle_seconds,
        listen_max_messages=listen_max_messages,
        earlier=earlier,
    )
