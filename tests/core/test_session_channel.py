from vanessa.core.messages import StoredMessage
from vanessa.core.session.channel_keys import CHANNEL_TELEGRAM, CHANNEL_VRCHAT
from vanessa.core.session.chat_session_state import load_chat_session_state


class _ChannelRepo:
    def __init__(self, messages: list[StoredMessage]) -> None:
        self.messages = messages
        self.requested_channel: str | None = None

    async def get_recent(
        self,
        limit: int = 50,
        *,
        channel: str = CHANNEL_TELEGRAM,
    ) -> list[StoredMessage]:
        self.requested_channel = channel
        matched = [message for message in self.messages if message.channel == channel]
        return matched[-limit:]


async def test_telegram_session_window_skips_vrchat_rows():
    repo = _ChannelRepo(
        [
            StoredMessage(id=1, role="user", content="tg", channel=CHANNEL_TELEGRAM),
            StoredMessage(id=2, role="user", content="vr", channel=CHANNEL_VRCHAT),
            StoredMessage(
                id=3,
                role="assistant",
                content="tg-reply",
                channel=CHANNEL_TELEGRAM,
            ),
        ]
    )
    state = await load_chat_session_state(
        repo,
        window_size=50,
        max_idle_seconds=0,
        listen_max_messages=3,
        channel=CHANNEL_TELEGRAM,
    )
    assert repo.requested_channel == CHANNEL_TELEGRAM
    contents = [message.content for message in state.messages]
    assert "vr" not in contents
    assert contents == ["tg", "tg-reply"]


async def test_vrchat_session_window_skips_telegram_rows():
    repo = _ChannelRepo(
        [
            StoredMessage(id=1, role="user", content="tg", channel=CHANNEL_TELEGRAM),
            StoredMessage(id=2, role="user", content="vr", channel=CHANNEL_VRCHAT),
        ]
    )
    state = await load_chat_session_state(
        repo,
        window_size=50,
        max_idle_seconds=0,
        listen_max_messages=3,
        channel=CHANNEL_VRCHAT,
    )
    assert [message.content for message in state.messages] == ["vr"]
