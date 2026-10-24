"""Detector for a reply that promises a later lookup result."""

import pytest

from vanessa.pipeline.llm.format.later_promise import promises_later_result


@pytest.mark.parametrize(
    "text",
    [
        "Ща гляну, что ты там наворотил за день — скину списком",
        "Погоди, найду — скину",
        "Сейчас проверю",
        "щас посмотрю",
        "Отпишусь потом",
        "Скину тебе позже",
        "Поищу и пришлю",
    ],
)
def test_promise_detected(text: str) -> None:
    assert promises_later_result(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Тут я. Чего надо?",
        "Посмотрю этот фильм",
        "Сейчас уже поздно",
        "Скину с балкона",
        "Не могу сейчас глянуть, спроси владельца",
    ],
)
def test_no_promise(text: str) -> None:
    assert promises_later_result(text) is False
