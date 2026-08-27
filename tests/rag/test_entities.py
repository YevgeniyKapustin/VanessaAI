from app.core.messages import ContextMessage
from app.knowledge.entities import (
    is_person_focused,
    mentioned_people_in_text,
    resolve_mentioned_people,
)


def _people_index(aliases: dict[str, str]) -> dict:
    """Build a People index manifest with ``aliases -> {"id", "file"}`` entries."""
    index: dict = {"aliases": {}}
    for alias, file in aliases.items():
        note_id = file.replace("People/", "").replace(".md", "")
        index["aliases"][alias.lower()] = {"id": note_id, "file": file}
    return index


def _message(content: str, message_id: int = 1) -> ContextMessage:
    return ContextMessage(id=message_id, role="user", content=content)


def test_mentioned_people_matches_alias() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    assert mentioned_people_in_text("что там у лича", index) == ["People/личь.md"]


def test_mentioned_people_orders_by_alias_map() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    assert mentioned_people_in_text("крабер и личь", index) == [
        "People/крабер.md",
        "People/личь.md",
    ]


def test_mentioned_people_matches_inflected_forms() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    # Russian inflections: «крабера», «лича» must resolve to the cards.
    assert mentioned_people_in_text("расскажи про крабера", index) == [
        "People/крабер.md"
    ]
    assert mentioned_people_in_text("а что у лича", index) == ["People/личь.md"]


def test_mentioned_people_no_match_for_plain_text() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    assert mentioned_people_in_text("просто обсуждение игры", index) == []


def test_mentioned_people_multialias_dedupes_files() -> None:
    index = _people_index(
        {"Личь": "People/личь.md", "Лич": "People/личь.md", "личный": "People/личь.md"}
    )
    assert mentioned_people_in_text("лич и лич", index) == ["People/личь.md"]


def test_resolve_current_message_first_then_recent() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    recent = [_message("крабер опять в пещере")]
    result = resolve_mentioned_people("а что у лича?", recent, index)
    assert result == ["People/личь.md", "People/крабер.md"]


def test_resolve_recent_window_is_bounded() -> None:
    index = _people_index(
        {"Личь": "People/личь.md", "Крабер": "People/крабер.md", "Котгаст": "People/котгаст.md"}
    )
    recent = [
        _message("котгаст злой", 1),
        _message("крабер весёлый", 2),
        _message("личь спокоен", 3),
    ]
    # Only the last 2 messages are scanned.
    result = resolve_mentioned_people("", recent, index, recent_window=2)
    assert result == ["People/крабер.md", "People/личь.md"]
    assert "People/котгаст.md" not in result


def test_resolve_empty_recent_returns_current() -> None:
    index = _people_index({"Личь": "People/личь.md", "Крабер": "People/крабер.md"})
    assert resolve_mentioned_people("расскажи про крабера", None, index) == [
        "People/крабер.md"
    ]


def test_resolve_returns_empty_for_no_mentions() -> None:
    index = _people_index({"Личь": "People/личь.md"})
    assert resolve_mentioned_people("привет всем", [_message("ок")], index) == []


def test_is_person_focused_question_word() -> None:
    assert is_person_focused("что там у лича с работой") is True
    assert is_person_focused("как у крабера дела") is True


def test_is_person_focused_prompt_phrase() -> None:
    assert is_person_focused("расскажи про крабера") is True
    assert is_person_focused("кто такой тик так") is True


def test_is_person_focused_casual_mention_false() -> None:
    assert is_person_focused("крабер пещеры") is False
    assert is_person_focused("личь опять молчит") is False
