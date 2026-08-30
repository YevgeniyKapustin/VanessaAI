from pathlib import Path

from vanessa.core.users import nicknames


def test_format_nicknames_for_planner_dedupes_repeated_display_names(monkeypatch):
    # Several Telegram accounts can share one display name (e.g. three different
    # users are all «Котгаст»). The planner prompt must list each name once,
    # while the full ID→name mapping stays in get_chat_nicknames() for mention
    # detection.
    monkeypatch.setattr(
        nicknames,
        "get_chat_nicknames",
        lambda: ("Котгаст", "Крабер", "Котгаст", "Личь", "Котгаст"),
    )
    assert nicknames.format_nicknames_for_planner() == "Котгаст, Крабер, Личь"


def test_format_nicknames_for_planner_sorted_case_insensitively(monkeypatch):
    monkeypatch.setattr(
        nicknames,
        "get_chat_nicknames",
        lambda: ("Вася", "андрей", "Гриша"),
    )
    assert nicknames.format_nicknames_for_planner() == "андрей, Вася, Гриша"


def test_format_nicknames_for_planner_empty(monkeypatch):
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ())
    assert nicknames.format_nicknames_for_planner() == "(не заданы)"


def test_canonical_name_for_resolves_alias_to_canonical(monkeypatch):
    monkeypatch.setattr(
        nicknames,
        "get_chat_aliases",
        lambda: {"Гриша": ("Ну я", "ну я", "гриша")},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))
    # A Telegram nickname («ну я») resolves to the name the chat uses.
    assert nicknames.canonical_name_for("Ну я") == "Гриша"
    # The canonical name resolves to itself.
    assert nicknames.canonical_name_for("Гриша") == "Гриша"
    # Unknown names stay unresolved.
    assert nicknames.canonical_name_for("Неизвестный") is None
    assert nicknames.canonical_name_for("") is None
    assert nicknames.canonical_name_for(None) is None


def test_find_nicknames_in_text_matches_alias(monkeypatch):
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))
    monkeypatch.setattr(
        nicknames,
        "get_chat_aliases",
        lambda: {"Гриша": ("Ну я",)},
    )
    found = nicknames.find_nicknames_in_text("что сказал ну я про игру")
    assert "Гриша" in found


def test_find_nicknames_in_text_does_not_duplicate_canonical(monkeypatch):
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))
    monkeypatch.setattr(
        nicknames,
        "get_chat_aliases",
        lambda: {"Гриша": ("Ну я", "гриша")},
    )
    found = nicknames.find_nicknames_in_text("гриша, ну я и гриша")
    assert found.count("Гриша") == 1


def test_format_aliases_for_prompt_renders_distinct_aliases(monkeypatch):
    monkeypatch.setattr(
        nicknames,
        "get_chat_aliases",
        lambda: {"Гриша": ("Ну я", "гриша")},
    )
    assert "Гриша = Ну я" in nicknames.format_aliases_for_prompt()


def test_format_aliases_for_prompt_empty(monkeypatch):
    monkeypatch.setattr(nicknames, "get_chat_aliases", lambda: {})
    assert nicknames.format_aliases_for_prompt() == ""


# ---------------------------------------------------------------------------
# Single source of truth: aliases come from the knowledge vault People cards,
# not from a separate aliases config. Editing a card is enough.
# ---------------------------------------------------------------------------


def _write_people_card(tmp_path: Path, filename: str, telegram_id: str, aliases: list[str]) -> None:
    people = tmp_path / "People"
    people.mkdir(parents=True, exist_ok=True)
    card = people / filename
    aliases_block = "\n".join(f"- {alias}" for alias in aliases)
    card.write_text(
        f"---\ntype: person\nid: {Path(filename).stem}\naliases:\n{aliases_block}\n"
        f"telegram_id: '{telegram_id}'\n---\n\n## Контекст жизни\n",
        encoding="utf-8",
    )


def test_get_chat_aliases_reads_from_vault_people_cards(monkeypatch, tmp_path):
    _write_people_card(tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"])
    _write_people_card(tmp_path, "крабер.md", "7030546957", ["Крабер", "Владимир"])
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша", 7030546957: "Крабер"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша", "Крабер"))

    aliases = nicknames.get_chat_aliases()
    assert aliases["Гриша"] == ("Ну я",)
    assert aliases["Крабер"] == ("Владимир",)


def test_canonical_name_for_uses_vault_aliases(monkeypatch, tmp_path):
    _write_people_card(tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"])
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    # The vault card carries the alias, so the raw Telegram nickname resolves.
    assert nicknames.canonical_name_for("Ну я") == "Гриша"
    assert nicknames.canonical_name_for("ну я") == "Гриша"
    assert nicknames.canonical_name_for("Гриша") == "Гриша"


def test_format_aliases_for_prompt_uses_vault_aliases(monkeypatch, tmp_path):
    _write_people_card(tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"])
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    assert "Гриша = Ну я" in nicknames.format_aliases_for_prompt()


# ---------------------------------------------------------------------------
# Telegram @username: the People card carries a dedicated frontmatter field
# (``telegram_username`` / ``username``, e.g. ``nu_ya`` for ``@nu_ya``) which is
# read as an alias on top of ``aliases``/``names`` — the vault stays the single
# source of truth.
# ---------------------------------------------------------------------------


def _write_people_card_with_username(
    tmp_path: Path,
    filename: str,
    telegram_id: str,
    aliases: list[str],
    username: str,
) -> None:
    people = tmp_path / "People"
    people.mkdir(parents=True, exist_ok=True)
    card = people / filename
    aliases_block = "\n".join(f"- {alias}" for alias in aliases)
    card.write_text(
        f"---\ntype: person\nid: {Path(filename).stem}\naliases:\n{aliases_block}\n"
        f"telegram_id: '{telegram_id}'\ntelegram_username: '{username}'\n"
        f"---\n\n## Контекст жизни\n",
        encoding="utf-8",
    )


def test_get_chat_aliases_reads_telegram_username_field(monkeypatch, tmp_path):
    _write_people_card_with_username(
        tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"], "nu_ya"
    )
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    # aliases («Ну я») + the dedicated @username field, all resolving to «Гриша».
    aliases = nicknames.get_chat_aliases()
    assert aliases["Гриша"] == ("Ну я", "nu_ya")


def test_canonical_name_for_resolves_telegram_username(monkeypatch, tmp_path):
    _write_people_card_with_username(
        tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"], "nu_ya"
    )
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    # The chat alias («Ну я») and both forms of the @username resolve.
    assert nicknames.canonical_name_for("Ну я") == "Гриша"
    assert nicknames.canonical_name_for("nu_ya") == "Гриша"
    assert nicknames.canonical_name_for("@nu_ya") == "Гриша"


def test_get_chat_aliases_merges_aliases_with_telegram_username(monkeypatch, tmp_path):
    _write_people_card_with_username(
        tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"], "nu_ya"
    )
    _write_people_card_with_username(
        tmp_path, "крабер.md", "7030546957", ["Крабер", "Владимир"], "kraber"
    )
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша", 7030546957: "Крабер"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша", "Крабер"))

    aliases = nicknames.get_chat_aliases()
    assert aliases["Гриша"] == ("Ну я", "nu_ya")
    assert aliases["Крабер"] == ("Владимир", "kraber")


def test_format_aliases_for_prompt_includes_telegram_username(monkeypatch, tmp_path):
    _write_people_card_with_username(
        tmp_path, "гриша.md", "1071793838", ["Гриша", "Ну я"], "nu_ya"
    )
    monkeypatch.setattr(nicknames.settings, "knowledge_path", str(tmp_path))
    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(nicknames, "get_chat_nicknames", lambda: ("Гриша",))

    assert "Гриша = Ну я, nu_ya" in nicknames.format_aliases_for_prompt()


async def test_get_chat_aliases_skips_sync_postgres_on_running_loop(monkeypatch):
    nicknames._ALIAS_CACHE = (("cached",), {"Гриша": ("Ну я",)})

    def boom(*_args, **_kwargs):
        raise AssertionError("sync vault must not run on the event loop")

    monkeypatch.setattr(nicknames, "_people_signature", boom)
    monkeypatch.setattr(nicknames, "_iter_people_notes", boom)
    assert nicknames.get_chat_aliases() == {"Гриша": ("Ну я",)}
    nicknames._ALIAS_CACHE = None


async def test_ensure_people_alias_cache_uses_async_vault(monkeypatch):
    class _Vault:
        is_configured = True

        async def notes_signature(self, folder):
            return ("sig",)

        async def list_notes(self, folder):
            from vanessa.knowledge.schema import VaultNote

            return [
                VaultNote(
                    relative_path="People/гриша.md",
                    meta={
                        "telegram_id": "1071793838",
                        "aliases": ["Гриша", "Ну я"],
                    },
                    body="",
                    updated_at=0.0,
                )
            ]

    monkeypatch.setattr(
        nicknames,
        "load_nicknames",
        lambda _: {1071793838: "Гриша"},
    )
    monkeypatch.setattr(
        "vanessa.knowledge.vault.KnowledgeVault",
        lambda *a, **k: _Vault(),
    )
    nicknames._ALIAS_CACHE = None
    await nicknames.ensure_people_alias_cache()
    assert nicknames.get_chat_aliases()["Гриша"] == ("Ну я",)
    nicknames._ALIAS_CACHE = None
