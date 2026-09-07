from datetime import date

from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.memory import compaction as compaction_mod
from vanessa.knowledge.memory.compaction import (
    compact_all_person_cards,
    compact_person_card,
)
from vanessa.knowledge.memory.compaction_archive import append_archive
from vanessa.knowledge.schema import VaultNote

TODAY = date(2026, 9, 8)


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
            meta=meta,
            body=body,
        )
        return relative_path

    async def list_notes(self, folder: str, *, recursive: bool = False):
        del recursive
        prefix = folder.rstrip("/") + "/"
        return [
            note
            for path, note in self.notes.items()
            if path.startswith(prefix)
        ]


def _card(person_id: str, body: str) -> VaultNote:
    rel = f"{PEOPLE}/{person_id}.md"
    return VaultNote(relative_path=rel, meta={"id": person_id, "type": "person"}, body=body)


async def test_compact_person_missing_note() -> None:
    kept, archived, changed = await compact_person_card(_Vault(), "ghost", today_=TODAY)
    assert (kept, archived, changed) == (0, 0, False)


async def test_compact_person_archives_overflow() -> None:
    body = "## Контекст жизни\n" + "\n".join(
        f"- 2024-01-{day:02d}: fact {day}" for day in range(1, 16)
    )
    vault = _Vault()
    note = _card("ada", body)
    vault.notes[note.relative_path] = note
    min_kept = 2
    kept, archived, changed = await compact_person_card(
        vault, "ada", today_=TODAY, limit=min_kept
    )
    assert changed is True
    assert archived > 0
    assert kept >= min_kept
    archive = await vault.read_note("_archive/People/ada.md")
    assert archive is not None


async def test_compact_person_unchanged_body() -> None:
    vault = _Vault()
    note = _card("ada", "## Хроника\n- stay\n")
    vault.notes[note.relative_path] = note
    kept, archived, changed = await compact_person_card(vault, "ada", today_=TODAY)
    assert changed is False
    assert archived == 0
    assert kept >= 0


async def test_compact_all_skips_unconfigured() -> None:
    files, archived = await compact_all_person_cards(_Vault(configured=False))
    assert files == 0
    assert archived == 0


async def test_compact_all_swallows_card_errors(monkeypatch) -> None:
    vault = _Vault()
    vault.notes[f"{PEOPLE}/bad.md"] = _card("bad", "## Контекст жизни\n- 2024-01-01: x\n")

    async def boom(*_args, **_kwargs):
        raise RuntimeError("io")

    monkeypatch.setattr(compaction_mod, "compact_person_card", boom)
    files, archived = await compact_all_person_cards(vault, today_=TODAY)
    assert files == 0
    assert archived == 0


async def test_append_archive_dedupes() -> None:
    vault = _Vault()
    first = await append_archive(vault, "ada", "## Контекст жизни", ["- 2024-01-01: a"])
    second = await append_archive(vault, "ada", "## Контекст жизни", ["- 2024-01-01: a"])
    other = await append_archive(vault, "ada", "## Цитатник", ["> hi"])
    empty = await append_archive(vault, "ada", "## Цитатник", [])
    assert first == 1
    assert second == 0
    assert other == 1
    assert empty == 0
