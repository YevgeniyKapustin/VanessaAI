from vanessa.config.settings import settings
from vanessa.knowledge.metrics.feedback import render_feedback_block
from vanessa.knowledge.metrics.schema import PersonMetrics


def test_feedback_block_lists_card_facts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "feedback_tone_enabled", True)

    block = render_feedback_block(
        name="Ada",
        metrics=PersonMetrics.zero(),
        mood="calm",
        facts=("пишет бэкенд", "живёт в Лондоне"),
    )

    assert block is not None
    first, second = block.splitlines()
    assert first.startswith("- Ada:")
    assert second == "  facts about Ada: пишет бэкенд; живёт в Лондоне"


def test_feedback_block_without_facts_is_one_line(monkeypatch) -> None:
    monkeypatch.setattr(settings, "feedback_tone_enabled", True)

    block = render_feedback_block(name="Ada", metrics=PersonMetrics.zero())

    assert block is not None
    assert "\n" not in block
