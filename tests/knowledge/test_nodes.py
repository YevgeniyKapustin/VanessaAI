from datetime import UTC, date, datetime
from types import SimpleNamespace

from vanessa.knowledge.nodes.node import (
    node_to_note,
    note_to_node,
    note_to_row_values,
)
from vanessa.knowledge.nodes.node_convert import (
    as_int_list,
    date_from_text,
    parse_date,
    row_to_note,
    try_int,
)
from vanessa.knowledge.nodes.node_schema import (
    extra_metadata,
    folder_of,
    slug_of,
    type_of,
)
from vanessa.knowledge.nodes.service import KnowledgeService
from vanessa.knowledge.schema import VaultNote


def test_try_int_and_int_list() -> None:
    parsed = 3
    assert try_int("3") == parsed
    assert try_int("x") is None
    assert as_int_list(None) == []
    assert as_int_list(5) == [5]
    assert as_int_list([1, 1, "x", 2]) == [1, 2]


def test_dates_and_row_to_note() -> None:
    fallback = date(2026, 1, 1)
    assert date_from_text("", fallback) == fallback
    assert date_from_text("2026-09-08", fallback) == date(2026, 9, 8)
    assert date_from_text("nope", fallback) == fallback
    assert parse_date(datetime(2026, 2, 3, tzinfo=UTC), fallback) == date(2026, 2, 3)
    assert parse_date(date(2026, 2, 3), fallback) == date(2026, 2, 3)
    now = datetime(2026, 9, 8, tzinfo=UTC)
    row = SimpleNamespace(
        id="People/ada.md",
        slug="ada",
        type="person",
        title="Ada",
        aliases=["Ada"],
        metadata_={"mood": "calm"},
        content="hello",
        source_message_ids=[9],
        created_at=now,
        updated_at=now,
    )
    note = row_to_note(row)
    assert note.relative_path == "People/ada.md"
    assert note.meta["id"] == "ada"
    assert note.body == "hello"
    empty = row_to_note(
        SimpleNamespace(
            id="x.md",
            slug=None,
            type=None,
            title=None,
            aliases=None,
            metadata_=None,
            content=None,
            source_message_ids=None,
            created_at=None,
            updated_at=None,
        )
    )
    assert empty.body == ""


def test_schema_path_helpers() -> None:
    assert folder_of("People/ada.md") == "People"
    assert folder_of("ada.md") == ""
    assert slug_of("People/ada.md", {"id": "ada"}) == "ada"
    assert slug_of("People/ada.md", {}) == "ada"
    assert type_of("People/ada.md", {"type": "person"}) == "person"
    assert type_of("People/ada.md", {}) == "person"
    assert type_of("Culture/movies/x.md", {}) == "recommendation"
    assert type_of("Logs/weekly/w.md", {}) == "log"
    assert type_of("_archive/People/a.md", {}) == "archive"
    assert type_of("inbox/a.md", {}) == "note"
    extra = extra_metadata({"id": "a", "type": "person", "mood": "x"})
    assert extra == {"mood": "x"}


def test_note_node_roundtrip() -> None:
    note = VaultNote(
        relative_path="People/ada.md",
        meta={
            "id": "ada",
            "type": "person",
            "title": "Ada",
            "aliases": ["Ada"],
            "names": ["A"],
            "created": "2026-01-01",
            "updated": "2026-09-01",
            "source_message_ids": [1],
            "mood": "calm",
        },
        body="body",
    )
    values = note_to_row_values(note)
    assert values["folder"] == "People"
    assert values["slug"] == "ada"
    node = note_to_node(note)
    assert node.relative_path == "People/ada.md"
    back = node_to_note(node)
    assert back.meta["id"] == "ada"
    assert back.body == "body"


class _EmptyResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def __iter__(self):
        return iter([])


async def test_knowledge_service_get_missing() -> None:
    session = SimpleNamespace()

    async def missing(_cls, _key):
        return None

    session.get = missing
    service = KnowledgeService(session)
    assert await service.get("missing") is None
    assert await service.get_note("missing") is None


async def test_knowledge_service_search_empty() -> None:
    session = SimpleNamespace()

    async def missing(_cls, _key):
        return None

    async def execute(_stmt):
        return _EmptyResult()

    session.get = missing
    session.execute = execute
    service = KnowledgeService(session)
    assert await service.search_fts("  ") == []
    assert await service.search_aliases("  ") == []
    assert await service.read_document("x") == {}
