from unittest.mock import AsyncMock, MagicMock

from services.agent.container.retrieval.knowledge import KnowledgeGraph
from vanessa.config.settings import settings
from vanessa.knowledge.pinned import PinnedNotes, pinned_text, pinned_title
from vanessa.knowledge.schema import VaultNote
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.vault import KnowledgeVault

CLIP = 20
BODY = (
    "## Контекст жизни\n"
    "- 2026-01-02: Ада — тимлид\n"
    "\n"
    "## Состав\n"
    "- Ада — тимлид\n"
    "- Боб — QA\n"
    "## Цитатник\n"
    "\n"
    "## Хроника\n"
)


def test_pinned_text_drops_blank_lines_and_empty_sections() -> None:
    text = pinned_text(BODY, 0)
    assert "Цитатник" not in text
    assert "Хроника" not in text
    assert text.startswith("## Контекст жизни\n  - 2026-01-02")
    assert "\n  - Боб — QA" in text


def test_pinned_text_clips_long_body() -> None:
    text = pinned_text(BODY, CLIP)
    assert len(text) <= CLIP + 1
    assert text.endswith("…")
    assert pinned_text("", CLIP) == ""


def test_pinned_title_prefers_nickname_then_title_then_stem() -> None:
    note = VaultNote("People/team.md", {"nickname": "Команда", "title": "T"})
    assert pinned_title(note) == "Команда"
    assert pinned_title(VaultNote("People/team.md", {"title": "T"})) == "T"
    assert pinned_title(VaultNote("People/team.md")) == "team"


async def test_pinned_notes_read_vault_and_skip_missing(tmp_path) -> None:
    vault = KnowledgeVault(store=FilesystemKnowledgeStore(str(tmp_path)))
    await vault.ensure_structure()
    await vault.write_note(
        "People/team.md",
        {"id": "team", "type": "person", "nickname": "Команда"},
        BODY,
        mutation_source="test",
    )
    await vault.write_note("People/empty.md", {"id": "empty"}, "\n## Хроника\n")
    pinned = PinnedNotes(
        vault,
        ["People/team.md", "People/none.md", "People/empty.md"],
        max_chars=500,
    )
    blocks = await pinned.blocks()
    assert len(blocks) == 1
    assert blocks[0].path == "People/team.md"
    assert blocks[0].title == "Команда"
    assert blocks[0].kind == "note"
    assert "Боб — QA" in blocks[0].content


async def test_pinned_notes_read_error_fails_open() -> None:
    vault = MagicMock()
    vault.read_note = AsyncMock(side_effect=RuntimeError("db down"))
    pinned = PinnedNotes(vault, ["People/team.md"], max_chars=500)
    assert await pinned.blocks() == []


def test_settings_parse_pinned_paths(monkeypatch) -> None:
    monkeypatch.setattr(settings, "knowledge_pinned_notes", " a.md, ,b.md ")
    assert settings.pinned_note_paths == ("a.md", "b.md")


def test_knowledge_graph_pinned_notes_follow_settings(monkeypatch) -> None:
    graph = KnowledgeGraph(vault=MagicMock(), index=MagicMock())
    monkeypatch.setattr(settings, "knowledge_pinned_notes", "")
    assert graph.pinned_notes() is None
    monkeypatch.setattr(settings, "knowledge_pinned_notes", "People/team.md")
    assert isinstance(graph.pinned_notes(), PinnedNotes)
