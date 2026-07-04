from dataclasses import dataclass

from aiogram.types import Message as TelegramMessage

from app.bot.addressing import _bot_username, extract_addressing


@dataclass
class FakeUser:
    id: int
    username: str | None = None


@dataclass
class FakeBot:
    id: int
    _me: FakeUser | None = None


def test_bot_username_uses_cached_me():
    bot = FakeBot(id=42, _me=FakeUser(id=42, username="VanessaBot"))

    assert _bot_username(bot) == "vanessabot"


def test_bot_username_missing_me():
    bot = FakeBot(id=42)

    assert _bot_username(bot) == ""


def test_extract_addressing_reply_to_bot_without_bot_username():
    bot_user = FakeUser(id=8294736159)
    human = FakeUser(id=1)
    reply = type("Reply", (), {"from_user": bot_user})()
    message = type(
        "Message",
        (),
        {
            "bot": FakeBot(id=8294736159),
            "text": "да именно",
            "reply_to_message": reply,
            "entities": None,
        },
    )()

    signals = extract_addressing(message)  # type: ignore[arg-type]

    assert signals.reply_to_bot is True
    assert signals.mentions_bot is False
