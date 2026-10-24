from dataclasses import dataclass

from vanessa.config.content import get_content


@dataclass(frozen=True, slots=True)
class ConversationConfig:
    session_window_size: int
    session_idle_seconds: float
    post_reply_listen_count: int
    session_earlier_count: int = 0
    session_earlier_max_seconds: float = 0


def load_conversation_config() -> ConversationConfig:
    conversation = get_content().conversation
    return ConversationConfig(
        session_window_size=conversation.session_window_size,
        session_idle_seconds=float(conversation.session_idle_seconds),
        post_reply_listen_count=conversation.post_reply_listen_count,
        session_earlier_count=conversation.session_earlier_count,
        session_earlier_max_seconds=float(conversation.session_earlier_max_seconds),
    )
