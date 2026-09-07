from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.memory.writer import KnowledgeVaultWriter
from vanessa.knowledge.memory.writer_fields import (
    first_str,
    list_or_default,
    note_body,
    stripped_text,
)
from vanessa.knowledge.memory.writer_merge import (
    append_to_section,
    as_list,
    attach_telegram_id,
    merge_meta,
)
from vanessa.knowledge.memory.writer_recommendation import (
    recommendation_meta,
    recommendation_status,
    recommendation_target,
)
from vanessa.knowledge.schema import MemoryPlan, VaultNote


class _Vault:
    def __init__(self, *, configured: bool = True) -> None:
        self.is_configured = configured
        self.notes: dict[str, VaultNote] = {}

    async def read_note(self, relative_path: str) -> VaultNote | None:
        return self.notes.get(relative_path)

    async def write_note(
        self,
        relative_path: str,
        meta: dict,
        body: str,
        mutation_source: str = "direct",
    ) -> str:
        del mutation_source
        self.notes[relative_path] = VaultNote(
            relative_path=relative_path,
            meta=dict(meta),
            body=body,
        )
        return relative_path


class _Index:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}
        self.rebuilt: list[str] = []

    async def load_folder(self, folder: str) -> dict:
        del folder
        return self.data

    async def rebuild_folder(self, folder: str) -> dict:
        self.rebuilt.append(folder)
        return {}


def test_merge_helpers() -> None:
    assert as_list(None) == []
    assert as_list("a") == ["a"]
    assert as_list(["a", "b"]) == ["a", "b"]
    meta: dict = {}
    telegram_id = 7
    attach_telegram_id(meta, telegram_id, "ada")
    assert meta["telegram_id"] == telegram_id
    body = append_to_section("", "## Цитатник", ["> hi", "> hi", ""])
    assert "> hi" in body
    again = append_to_section(body, "## Цитатник", ["> hi"])
    assert again == body
    merged = merge_meta(
        {"aliases": ["Ada"], "created": "2026-01-01", "source_message_ids": [1]},
        {"aliases": ["Ada", "A"], "created": "2026-09-01"},
        [1, 2, "x"],
    )
    extra_id = 2
    assert merged["created"] == "2026-01-01"
    assert "A" in merged["aliases"]
    assert extra_id in merged["source_message_ids"]


def test_writer_fields_and_recommendation() -> None:
    assert first_str("", None, "x") == "x"
    assert first_str() == ""
    assert stripped_text("  y  ") == "y"
    assert note_body(None) == ""
    assert note_body(VaultNote("p", body="b")) == "b"
    assert list_or_default(None, ["d"]) == ["d"]
    assert recommendation_target({"kind": "nope", "title": "x"}) is None
    assert recommendation_target({"kind": "movies"}) is None
    target = recommendation_target({"kind": "movies", "title": "Blade"})
    assert target is not None
    assert recommendation_status({"status": "watched"}, None) == "watched"
    assert recommendation_status({}, None) == "proposed"
    existing = VaultNote("p", meta={"status": "queued"})
    assert recommendation_status({}, existing) == "queued"
    meta = recommendation_meta(
        {"recommended_by": "Ada", "rating": 5},
        note_id="blade",
        kind="movies",
        title="Blade",
        status="proposed",
    )
    rating = 5
    assert meta["rating"] == rating
    assert meta["kind"] == "movies"


async def test_writer_apply_empty_or_unconfigured() -> None:
    writer = KnowledgeVaultWriter(_Vault(configured=False), _Index())
    assert await writer.apply(MemoryPlan(updates=({"type": "quote"},))) == 0
    writer = KnowledgeVaultWriter(_Vault(), _Index())
    assert await writer.apply(MemoryPlan()) == 0


async def test_writer_quote_person_glossary_event() -> None:
    vault = _Vault()
    index = _Index()
    writer = KnowledgeVaultWriter(vault, index)
    plan = MemoryPlan(
        updates=(
            {"type": "quote", "person": "Ada", "quote": "hi", "context": "chat"},
            {"type": "person_fact", "person": "Ada", "text": "plays vr", "section": "context"},
            {"type": "person_mood", "person": "Ada", "mood": "calm"},
            {"type": "glossary", "term": "OSC", "definition": "protocol", "first_quote": "osc"},
            {
                "type": "event",
                "title": "Party",
                "summary": "danced",
                "outcome": "fun",
                "date": "2026-09-01",
            },
            {"type": "recommendation", "kind": "movies", "title": "Blade", "description": "cool"},
            {"type": "weekly_summary", "summary": "busy week"},
            {"type": "unknown"},
            "not-a-dict",
        )
    )
    written = await writer.apply(plan, source_message_ids=[9])
    assert written >= 1
    assert any(path.startswith(f"{PEOPLE}/") for path in vault.notes)
    assert PEOPLE in index.rebuilt


async def test_writer_vrchat_quote_skips_telegram_bind() -> None:
    vault = _Vault()
    writer = KnowledgeVaultWriter(vault, _Index())
    plan = MemoryPlan(
        updates=(
            {
                "type": "quote",
                "person": "UnjoinedVrName",
                "quote": "yo",
                "channel": "vrchat",
            },
        )
    )
    await writer.apply(plan)
    note = next(iter(vault.notes.values()))
    assert "telegram_id" not in note.meta


async def test_writer_skips_blank_person_and_swallows_update_error() -> None:
    vault = _Vault()
    writer = KnowledgeVaultWriter(vault, _Index())
    plan = MemoryPlan(
        updates=(
            {"type": "quote", "person": "", "quote": "x"},
            {"type": "person_fact", "person": ""},
            {"type": "glossary", "term": ""},
            {"type": "event", "title": ""},
            {"type": "weekly_summary", "summary": ""},
        )
    )
    await writer.apply(plan)
    assert vault.notes == {}

    async def boom(*_a, **_k):
        raise RuntimeError("write")

    writer._apply_update = boom  # type: ignore[method-assign]
    await writer.apply(
        MemoryPlan(updates=({"type": "quote", "person": "A", "quote": "q"},))
    )
    assert "People/a.md" not in vault.notes


async def test_writer_vector_reindex(monkeypatch) -> None:
    vault = _Vault()
    indexed: list[str] = []

    class Vectors:
        async def index_note(self, path: str) -> None:
            indexed.append(path)
            if path.endswith("_index.yaml"):
                raise RuntimeError("skip")

    writer = KnowledgeVaultWriter(vault, _Index(), vector_indexer=Vectors())
    plan = MemoryPlan(updates=({"type": "quote", "person": "Ada", "quote": "hi"},))
    await writer.apply(plan)
    assert indexed
