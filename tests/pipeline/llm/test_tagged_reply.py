"""Only an explicit final-answer boundary permits compose output to be sent."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.pipeline.llm.tagged_reply import (
    UNTAGGED_ATTEMPTS,
    UntaggedReplyError,
    raise_if_untagged,
    request_tagged,
    split_reply,
)

UNTAGGED = [
    # Production leak on 2026-10-26, missed by the old phrase detector.
    (
        "Обычное «привет» от владельца — коротко поздороваться, без разгона. "
        "Можно стикер-приветствие."
    ),
    "Он просто зовёт по имени. Отвечаю сухо",
    "He asks to set a reminder. Short reply.",
    "Привет",
    "Ставлю. Каждую пятницу в 13:00 буду кидать меню",
    "Глянь сюда: https://example.com/dashboard",
    "```\n[answer]\nэто пример формата, затем продолжение черновика\n```",
]


@pytest.mark.parametrize("text", UNTAGGED)
def test_untagged_output_never_becomes_a_reply(text: str) -> None:
    assert split_reply(text, "m") == ("", "")
    with pytest.raises(UntaggedReplyError):
        raise_if_untagged(text, "m")


@pytest.mark.parametrize("text", UNTAGGED)
async def test_untagged_output_gets_one_strict_retry(text: str) -> None:
    create = AsyncMock(
        side_effect=[MagicMock(text=text), MagicMock(text="[answer]\nПривет")]
    )
    response = await request_tagged(create, lambda r: r.text, model="m")
    assert response.text == "[answer]\nПривет"
    assert [call.kwargs["strict"] for call in create.await_args_list] == [False, True]


async def test_repeated_untagged_output_is_rejected_after_retry() -> None:
    create = AsyncMock(return_value=MagicMock(text=UNTAGGED[0]))
    response = await request_tagged(create, lambda r: r.text, model="m")
    assert create.await_count == UNTAGGED_ATTEMPTS
    with pytest.raises(UntaggedReplyError):
        raise_if_untagged(response.text, "m")


@pytest.mark.parametrize(
    ("raw", "reply"),
    [
        (f"{UNTAGGED[0]}\n[answer]\nПривет", "Привет"),
        ("[answer]\nHello, how are you doing today?", "Hello, how are you doing today?"),
        ("[answer]\nРаз\n[next]\nДва", "Раз\n[next]\nДва"),
        ("черновик\n<answer>Привет</answer>", "Привет"),
        ("[ignore] повтор", "[ignore] повтор"),
        ("", ""),
    ],
)
async def test_tagged_answers_and_silence_keep_their_behavior(raw: str, reply: str) -> None:
    create = AsyncMock(return_value=MagicMock(text=raw))
    await request_tagged(create, lambda r: r.text, model="m")
    create.assert_awaited_once()
    raise_if_untagged(raw, "m")
    assert split_reply(raw, "m")[0] == reply
