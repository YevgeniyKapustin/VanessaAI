from app.core.messages import ContextMessage
from app.decision.gate.quote_echo import (
    is_recursive_quote_loop,
    messages_echo,
    quote_loop_depth,
)


BOT_LINE = (
    "Котгаст, ты уже третий круг, скоро Данте тебя запишет в отдельный котёл"
)
RECURSION_LINE = (
    "Котгаст, ты уже цитируешь мою цитату своей цитаты моей цитаты — "
    "это не беседа, это рекурсия без базового случая"
)


def test_messages_echo_detects_verbatim_quote():
    assert messages_echo(BOT_LINE, BOT_LINE) is True


def test_messages_echo_detects_near_verbatim():
    user = BOT_LINE.replace("котёл", "котел")
    assert messages_echo(user, BOT_LINE) is True


def test_messages_echo_rejects_short_reply():
    assert messages_echo("да именно", BOT_LINE) is False


def test_messages_echo_rejects_different_message():
    assert messages_echo("расскажи про unity", BOT_LINE) is False


def test_quote_loop_depth_counts_echo_chain():
    recent = [
        ContextMessage(id=1, role="assistant", content=BOT_LINE),
        ContextMessage(id=2, role="user", content=BOT_LINE),
        ContextMessage(id=3, role="assistant", content=RECURSION_LINE),
        ContextMessage(id=4, role="user", content=RECURSION_LINE),
    ]

    assert quote_loop_depth(recent) == 2


def test_is_recursive_quote_loop_on_reply_to_bot_echo():
    recent = [
        ContextMessage(id=1, role="assistant", content=BOT_LINE),
    ]

    assert is_recursive_quote_loop(
        BOT_LINE,
        recent,
        reply_to_bot=True,
    ) is True


def test_is_recursive_quote_loop_on_second_echo_in_chain():
    recent = [
        ContextMessage(id=1, role="assistant", content=BOT_LINE),
        ContextMessage(id=2, role="user", content=BOT_LINE),
        ContextMessage(id=3, role="assistant", content=RECURSION_LINE),
    ]

    assert is_recursive_quote_loop(
        RECURSION_LINE,
        recent,
        reply_to_bot=True,
    ) is True


def test_is_recursive_quote_loop_allows_substantive_addition():
    recent = [
        ContextMessage(id=1, role="assistant", content=BOT_LINE),
    ]
    user = f"{BOT_LINE} — это же неправда?"

    assert is_recursive_quote_loop(
        user,
        recent,
        reply_to_bot=True,
    ) is False
