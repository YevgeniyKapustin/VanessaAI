"""Untagged output: a clean reply is the answer, leaked reasoning is not."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from vanessa.pipeline.llm.format.reasoning_leak import (
    is_reasoning_leak,
    looks_like_reasoning,
)
from vanessa.pipeline.llm.tagged_reply import request_tagged, split_reply

# Real untagged `content` from deepseek-flash in thinking mode (live turn and
# the read-only replay); the reasoning was in `reasoning_content`.
CLEAN = [
    (
        "Ставлю. Каждую пятницу в 13:00 буду кидать меню — считай, обед уже "
        "решён за тебя."
    ),
    (
        "Тут особо рассказывать нечего: бот в телеге, живу на сервере в Лондоне, "
        "характер скверный. Дальше уже интереснее — могу копаться в рабочих "
        "системах: задачи в Plane, код в GitLab, логи в Grafana, поды в k8s.\n\n"
        "[next]\n\nСпросишь что-то по проекту — гляну и отпишусь отдельным "
        "сообщением.\n\n[sticker:tease]"
    ),
    (
        "Тут всё просто: я бот в телеге, не человек с телом и прогулками.\n\n"
        "[next]\n\nУмею: болтать и подкалывать, искать по твоим рабочим штукам — "
        "задачи в Plane, код в GitLab, k8s, графики в Grafana. Спросишь — гляну."
    ),
    (
        "Глянь сюда: [дашборд оплат](https://grafana.example.com/d/abc/payments"
        "?var-stand=qa&from=now-1h&to=now)"
    ),
    "Он спрашивал вчера про релиз, я помню",
    "Отвечаю, так и было",
    (
        "Работаю по твоим системам: задачи, код, логи. В чате — отвечу по делу, "
        "подколю, гомункулов в обиду не дам."
    ),
]
LEAKS = [
    (
        "Он просто зовёт по имени, без вопроса. Отвечаю сухо и коротко, без "
        "повторения объяснений"
    ),
    "He asks to set a recurring task. I should confirm — short reply, one line.",
    "Short confirmation. He's asking for a reminder, keep it in character.",
    "Это пост про обеды, перескажу коротко https://example.com/menu",
    "Надо ответить коротко и без подколов",
    "Пользователь спрашивает про задачи, нужно ответить списком",
    "should_reply=true, отвечу одной строкой",
    # Russian plan tails from `reasoning_content` of the replay.
    "Миша просит рассказать о себе, что умею. Ответить по делу, без воды",
    "Тон дерзкий. Не упоминать инструменты по именам",
    "Список длинный. Разбить на блоки",
]


@pytest.mark.parametrize("text", CLEAN)
def test_clean_untagged_reply_is_not_a_leak(text: str) -> None:
    assert not looks_like_reasoning(text)
    assert not is_reasoning_leak(text)
    assert split_reply(text, "m")[0] == text.strip()


@pytest.mark.parametrize("text", LEAKS)
def test_leaked_reasoning_is_silenced(text: str) -> None:
    assert is_reasoning_leak(text)
    assert split_reply(text, "m") == ("", "")


def test_tagged_output_is_never_a_leak() -> None:
    assert not is_reasoning_leak(f"{LEAKS[1]}\n[answer]\nГотово")


def _response(text: str) -> MagicMock:
    return MagicMock(text=text)


@pytest.mark.asyncio
async def test_clean_untagged_reply_is_not_retried(caplog) -> None:
    create = AsyncMock(return_value=_response(CLEAN[0]))
    response = await request_tagged(create, lambda r: r.text, model="m")
    assert response.text == CLEAN[0]
    create.assert_awaited_once()
    with caplog.at_level("INFO"):
        split_reply(CLEAN[0], "m")
    assert "llm_untagged_accepted" in caplog.text


@pytest.mark.asyncio
async def test_leak_is_retried_with_strict_flag() -> None:
    create = AsyncMock(side_effect=[_response(LEAKS[0]), _response("[answer]\nок")])
    response = await request_tagged(create, lambda r: r.text, model="m")
    assert response.text == "[answer]\nок"
    assert [call.kwargs["strict"] for call in create.await_args_list] == [False, True]
