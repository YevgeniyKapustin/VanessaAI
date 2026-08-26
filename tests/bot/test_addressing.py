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
    assert signals.reply_to_other_user is False
    assert signals.mentions_bot is False


def test_extract_addressing_reply_to_other_user():
    bot_user = FakeUser(id=1)
    other = FakeUser(id=99)
    reply = type("Reply", (), {"from_user": other})()
    message = type(
        "Message",
        (),
        {
            "bot": FakeBot(id=1),
            "text": "Личь не делает карты",
            "reply_to_message": reply,
            "entities": None,
        },
    )()

    signals = extract_addressing(message)  # type: ignore[arg-type]

    assert signals.reply_to_other_user is True
    assert signals.reply_to_bot is False


def test_extract_addressing_captures_replied_text_and_sender():
    bot_user = FakeUser(id=1)
    other = FakeUser(id=99, username="lich")
    reply = type(
        "Reply",
        (),
        {
            "from_user": other,
            "message_id": 555,
            "text": "Личь не делает карты",
        },
    )()
    message = type(
        "Message",
        (),
        {
            "bot": FakeBot(id=1),
            "text": "а я про то и говорю",
            "reply_to_message": reply,
            "entities": None,
        },
    )()

    signals = extract_addressing(message)  # type: ignore[arg-type]

    assert signals.reply_to_message_id == 555
    assert signals.reply_to_text == "Личь не делает карты"
    assert signals.reply_to_sender_name == "lich"
    assert signals.reply_to_sender_telegram_id == 99


def test_extract_addressing_reply_without_text_is_none():
    bot_user = FakeUser(id=1)
    other = FakeUser(id=99, username="lich")
    reply = type("Reply", (), {"from_user": other, "message_id": 556, "text": None})()
    message = type(
        "Message",
        (),
        {
            "bot": FakeBot(id=1),
            "text": "это к чему?",
            "reply_to_message": reply,
            "entities": None,
        },
    )()

    signals = extract_addressing(message)  # type: ignore[arg-type]

    assert signals.reply_to_text is None
    assert signals.reply_to_sender_name == "lich"


def test_extract_addressing_mention_in_text():
    message = type(
        "Message",
        (),
        {
            "bot": FakeBot(id=1, _me=FakeUser(id=1, username="VanessaBot")),
            "text": "Привет @VanessaBot",
            "reply_to_message": None,
            "entities": None,
        },
    )()

    signals = extract_addressing(message)  # type: ignore[arg-type]

    assert signals.mentions_bot is True
    assert signals.directly_addressed is True


def test_bot_username_from_bot_username_attr():
    bot = type("Bot", (), {"username": "DirectName"})()
    assert _bot_username(bot) == "directname"


def test_bot_username_none_bot():
    assert _bot_username(None) == ""
