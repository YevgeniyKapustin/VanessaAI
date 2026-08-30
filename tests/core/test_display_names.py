from datetime import datetime, timezone

from vanessa.knowledge.users.display_names import resolve_sender_display_name, resolve_user_display_name
from vanessa.core.messages import ContextMessage
from vanessa.infrastructure.ingest.user_backfill import load_nicknames
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder


def test_resolve_sender_uses_sender_name():
    assert resolve_sender_display_name(123, "Капустин") == "Капустин"


def test_resolve_sender_falls_back_to_telegram_id():
    assert resolve_sender_display_name(6765300380, None) == "6765300380"


def test_resolve_sender_canonicalizes_alias(monkeypatch):
    # A Telegram nickname «ну я» must render as the canonical «Гриша», so the
    # bot does not treat them as two different people.
    monkeypatch.setattr(
        "vanessa.knowledge.users.display_names.canonical_name_for",
        lambda alias: "Гриша" if alias in ("Ну я", "ну я", "гриша") else None,
    )
    assert resolve_sender_display_name(1071793838, "Ну я") == "Гриша"
    assert resolve_sender_display_name(1071793838, "Капустин") == "Капустин"


def test_resolve_user_display_name_canonicalizes_alias(monkeypatch):
    monkeypatch.setattr(
        "vanessa.knowledge.users.display_names.canonical_name_for",
        lambda alias: "Гриша" if alias in ("Ну я", "ну я", "гриша") else None,
    )
    assert (
        resolve_user_display_name(
            1071793838,
            nickname=None,
            first_name="Ну я",
            username="nu_ya",
        )
        == "Гриша"
    )


def test_resolve_user_display_name_prefers_nickname():
    assert resolve_user_display_name(
        7714154251,
        nickname="Евгений",
        first_name="Zhenya",
        username="kapustin",
    ) == "Евгений"


def test_resolve_sender_uses_vault_telegram_username(monkeypatch, tmp_path):
    # The People card declares that the Telegram @username «nu_ya» (and the
    # display name «Ну я») are the same person as «Гриша» — the sender renders
    # consistently from the vault (the single source of truth).

    from vanessa.knowledge.users import nicknames

    people = tmp_path / "People"
    people.mkdir(parents=True, exist_ok=True)
    (people / "гриша.md").write_text(
        "---\ntype: person\nid: гриша\n"
        "aliases:\n- Гриша\n- Ну я\n"
        "telegram_id: '1071793838'\ntelegram_username: 'nu_ya'\n"
        "---\n\n## Контекст жизни\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    assert resolve_sender_display_name(1071793838, "Ну я") == "Гриша"
    assert resolve_sender_display_name(1071793838, "nu_ya") == "Гриша"
    assert resolve_sender_display_name(1071793838, "@nu_ya") == "Гриша"
    assert resolve_sender_display_name(1071793838, "Капустин") == "Капустин"


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
    assert 'sender="Краб"' in line
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
