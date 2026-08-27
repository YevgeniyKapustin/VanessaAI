from app.core.users import nicknames


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
