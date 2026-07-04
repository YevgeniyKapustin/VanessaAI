from datetime import datetime, timezone

from app.core.users.display_names import resolve_sender_display_name, resolve_user_display_name
from app.core.messages import ContextMessage
from app.ingest.user_backfill import load_nicknames
from app.llm.prompts.prompt_builder import PromptBuilder


def test_resolve_sender_uses_sender_name():
    assert resolve_sender_display_name(123, "Капустин") == "Капустин"


def test_resolve_sender_falls_back_to_telegram_id():
    assert resolve_sender_display_name(6765300380, None) == "6765300380"


def test_resolve_user_display_name_prefers_nickname():
    assert resolve_user_display_name(
        7714154251,
        nickname="Евгений",
        first_name="Zhenya",
        username="kapustin",
    ) == "Евгений"


def test_prompt_builder_uses_sender_name():
    builder = PromptBuilder()
    line = builder.format_message_line(
        ContextMessage(
            id=1,
            role="user",
            content="привет",
            sender_telegram_id=6765300380,
            sender_name="Краб",
            created_at=datetime(2023, 5, 1, 14, 30, tzinfo=timezone.utc),
        )
    )
    assert "[user:Краб]" in line
    assert "6765300380" not in line


def test_load_nicknames(tmp_path):
    path = tmp_path / "nicknames.yaml"
    path.write_text(
        """
        7714154251: Евгений
        6765300380: Краб
        """,
        encoding="utf-8",
    )
    assert load_nicknames(path) == {
        7714154251: "Евгений",
        6765300380: "Краб",
    }
