from vanessa.knowledge.format import CULTURE, LOGS
from vanessa.knowledge.index.index import KnowledgeIndex
from vanessa.knowledge.index.index_build import (
    build_culture_index,
    build_events_index,
    build_glossary_index,
    build_inbox_index,
    build_logs_index,
    build_people_index,
)
from vanessa.knowledge.schema import VaultNote


def _note(path: str, **meta) -> VaultNote:
    return VaultNote(relative_path=path, meta=meta, body="body")


class _IndexVault:
    is_configured = True

    def __init__(self, yaml_store: dict[str, dict]) -> None:
        self.yaml_store = yaml_store

    async def notes_signature(self, folder: str) -> tuple:
        return (folder, 1)

    async def read_yaml(self, relative_path: str) -> dict:
        return self.yaml_store.get(relative_path, {"cached": True})

    async def write_yaml(self, relative_path: str, data: dict) -> str:
        self.yaml_store[relative_path] = data
        return relative_path

    async def list_notes(self, folder: str, **_k):
        if folder == "People":
            return [_note("People/ada.md", id="ada", aliases=["Ada"])]
        return []


def test_build_people_index_aliases_and_telegram() -> None:
    notes = [
        _note("People/ada.md", id="ada", telegram_id=1, aliases=["Ada"], names=["A"]),
        _note("People/other.md", id="other", telegram_id=1),
        _note("People/bob.md", id="bob", aliases="Bob"),
    ]
    people = build_people_index(notes)
    assert people["telegram_id"]["1"]["id"] == "ada"
    assert "ada" in people["aliases"] or "Ada".lower() in people["aliases"]


def test_build_glossary_events_inbox() -> None:
    glossary = build_glossary_index(
        [_note("Lore/glossary/osc.md", id="osc", aliases=["OSC"])]
    )
    assert "osc" in glossary["glossary"]["aliases"]
    events = build_events_index(
        [_note("Lore/events/party.md", id="party", date="2026-01-01", title="Party")]
    )
    assert events["events"][0]["title"] == "Party"
    inbox = build_inbox_index([_note("inbox/a.md", type="note")])
    assert inbox["notes"][0]["file"].endswith("a.md")


async def test_build_culture_and_logs_indexes() -> None:
    class Vault:
        async def list_notes(self, folder: str, **_k):
            if folder.startswith(f"{CULTURE}/"):
                kind = folder.rsplit("/", 1)[-1]
                return [_note(f"{folder}/x.md", id="x", title=kind, status="queued")]
            if folder.startswith(f"{LOGS}/"):
                return [_note(f"{folder}/w.md", period="weekly")]
            return []

    culture = await build_culture_index(Vault())
    assert "movies" in culture
    logs = await build_logs_index(Vault())
    assert "weekly" in logs or "daily" in logs


async def test_knowledge_index_load_and_rebuild() -> None:
    yaml_store: dict[str, dict] = {}
    index = KnowledgeIndex(_IndexVault(yaml_store))
    loaded = await index.load_folder("People")
    assert loaded["cached"] is True
    again = await index.load_folder("People")
    assert again == loaded
    rebuilt = await index.rebuild_folder("People")
    assert "aliases" in rebuilt or rebuilt == {}


async def test_knowledge_index_unconfigured_and_unknown() -> None:
    empty = KnowledgeIndex(
        type("V", (), {"is_configured": False})()  # type: ignore[arg-type]
    )
    assert await empty.load_folder("People") == {}
    assert await empty.rebuild_folder("People") == {}
    yaml_store: dict[str, dict] = {}
    unknown = await KnowledgeIndex(_IndexVault(yaml_store)).rebuild_folder("Unknown")
    assert unknown == {}
