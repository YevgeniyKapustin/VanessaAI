import pytest

from vanessa.pipeline.llm.planner.detail_detector import detect_detail_level


@pytest.mark.parametrize(
    "message",
    [
        "давай подробнее",
        "расскажи подробно про крабера",
        "поподробнее",
        "разверни ответ",
        "напиши развёрнуто",
        "объясни в деталях",
        "детальнее расскажи",
        "давай более развёрнутый ответ",
    ],
)
def test_detect_detail_level_detailed(message: str):
    assert detect_detail_level(message) == "detailed"


@pytest.mark.parametrize(
    "message",
    [
        "в двух словах",
        "скажи кратко",
        "без лишнего",
        "не растекайся",
        "вкратце",
        "кратенько",
        "без воды",
        "без простыни",
    ],
)
def test_detect_detail_level_brief(message: str):
    assert detect_detail_level(message) == "brief"


@pytest.mark.parametrize(
    "message",
    [
        "привет",
        "как дела",
        "объясни как это работает",
        "короче, расскажи про X",  # «короче» = discourse filler, not a brevity request
        "разверни приложение",  # «развернуть» = deploy, not "give details"
    ],
)
def test_detect_detail_level_normal(message: str):
    assert detect_detail_level(message) == "normal"


def test_detect_detail_level_more_detail_wins_over_brief():
    assert detect_detail_level("кратко, но подробнее") == "detailed"


def test_detect_detail_level_empty_message():
    assert detect_detail_level("") == "normal"
