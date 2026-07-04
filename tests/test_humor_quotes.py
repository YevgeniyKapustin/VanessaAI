from app.core.messages import ContextBlock, ContextMessage
from app.llm.humor_quotes import extract_humor_quotes


def test_extract_humor_quotes_prefers_running_jokes():
    blocks = [
        ContextBlock(
            anchor_id=2,
            messages=(
                ContextMessage(id=1, role="user", content="x" * 50),
                ContextMessage(
                    id=2,
                    role="user",
                    content="найди работу",
                    is_anchor=True,
                ),
            ),
        ),
        ContextBlock(
            anchor_id=3,
            messages=(
                ContextMessage(
                    id=3,
                    role="user",
                    content="капуста найди работу",
                ),
            ),
        ),
    ]

    quotes = extract_humor_quotes(blocks, max_quotes=3)

    assert set(quotes) == {"капуста найди работу", "найди работу"}


def test_extract_humor_quotes_filters_generic_insults():
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(
                    id=1,
                    role="user",
                    content="Ты просто лох",
                    is_anchor=True,
                ),
            ),
        ),
        ContextBlock(
            anchor_id=2,
            messages=(
                ContextMessage(
                    id=2,
                    role="user",
                    content="Я чисто из за времени пропущу так как раньше проходил",
                    is_anchor=True,
                ),
            ),
        ),
    ]

    assert extract_humor_quotes(blocks) == []


def test_extract_humor_quotes_boosts_reactions_after_punchline():
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(
                    id=1,
                    role="user",
                    content="Капуста самый няшный в этом чате",
                    is_anchor=True,
                ),
                ContextMessage(id=2, role="user", content="ахах согл"),
            ),
        ),
    ]

    quotes = extract_humor_quotes(blocks, max_quotes=1)

    assert quotes == ["Капуста самый няшный в этом чате"]


def test_extract_humor_quotes_filters_turbovladislav_noise():
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(
                    id=1,
                    role="user",
                    content="Паблики ко мне сначала обращаются",
                ),
            ),
        ),
        ContextBlock(
            anchor_id=2,
            messages=(
                ContextMessage(
                    id=2,
                    role="user",
                    content="привет ТУРБОВЛАДИСЛАВ",
                ),
            ),
        ),
        ContextBlock(
            anchor_id=3,
            messages=(
                ContextMessage(
                    id=3,
                    role="user",
                    content="Я принимаю тебя турбовладислав",
                ),
                ContextMessage(
                    id=4,
                    role="user",
                    content="да я вообще примитивный в пещере живу крабер",
                ),
                ContextMessage(
                    id=5,
                    role="user",
                    content="Ебать крабера под веществами",
                ),
            ),
        ),
    ]

    quotes = extract_humor_quotes(blocks, max_quotes=5)

    assert "Паблики ко мне сначала обращаются" not in quotes
    assert "привет ТУРБОВЛАДИСЛАВ" not in quotes
    assert "Я принимаю тебя турбовладислав" in quotes
    assert "да я вообще примитивный в пещере живу крабер" in quotes
    assert "Ебать крабера под веществами" in quotes


def test_extract_humor_quotes_skips_long_and_assistant():
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(id=1, role="assistant", content="я бот"),
                ContextMessage(
                    id=2,
                    role="user",
                    content="x" * 200,
                    is_anchor=True,
                ),
            ),
        ),
    ]

    assert extract_humor_quotes(blocks) == []
