"""A result posted lately answers a mere reaction to it, not a new question."""

from services.worker.hermes import dedupe
from vanessa.core import question_stems as core_stems
from vanessa.core.hermes_answers import MAX_PER_CHAT, RecentAnswers

CHAT_ID = -100
QUESTION = "какой статус деплоя сервиса после релиза?"
REPHRASE = "что со статусом деплоя сервиса после релиза"
OTHER = "сколько открытых задач в спринте команды?"
WINDOW = 600.0


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _answers(window: float = WINDOW) -> tuple[RecentAnswers, Clock]:
    clock = Clock()
    return RecentAnswers(window_seconds=window, clock=clock), clock


def test_reaction_after_a_fresh_result_is_covered() -> None:
    answers, _ = _answers()
    answers.note(CHAT_ID, QUESTION)
    assert answers.covers(CHAT_ID, REPHRASE, "ну и дела")


def test_old_result_does_not_cover() -> None:
    answers, clock = _answers()
    answers.note(CHAT_ID, QUESTION)
    clock.now += WINDOW + 1
    assert not answers.covers(CHAT_ID, REPHRASE, "ну и дела")


def test_user_naming_the_topic_asks_again() -> None:
    answers, _ = _answers()
    answers.note(CHAT_ID, QUESTION)
    assert not answers.covers(CHAT_ID, REPHRASE, "а что сейчас с деплоем?")


def test_another_topic_asks() -> None:
    answers, _ = _answers()
    answers.note(CHAT_ID, QUESTION)
    assert not answers.covers(CHAT_ID, OTHER, "ну и дела")


def test_another_chat_asks() -> None:
    answers, _ = _answers()
    answers.note(CHAT_ID, QUESTION)
    assert not answers.covers(CHAT_ID - 1, REPHRASE, "ну и дела")


def test_zero_window_keeps_nothing() -> None:
    answers, _ = _answers(window=0)
    answers.note(CHAT_ID, QUESTION)
    assert not answers.covers(CHAT_ID, QUESTION, "ну и дела")


def test_empty_question_keeps_nothing() -> None:
    answers, _ = _answers()
    answers.note(CHAT_ID, "ок")
    assert not answers.covers(CHAT_ID, QUESTION, "ну и дела")


def test_only_the_newest_answers_stay() -> None:
    answers, clock = _answers()
    answers.note(CHAT_ID, QUESTION)
    for index in range(MAX_PER_CHAT):
        clock.now += 1
        answers.note(CHAT_ID, f"{OTHER} номер{index}")
    assert not answers.covers(CHAT_ID, REPHRASE, "ну и дела")


def test_worker_dedupe_reuses_the_core_stems() -> None:
    assert dedupe.question_stems is core_stems.question_stems
    assert dedupe.is_rephrase is core_stems.is_rephrase
