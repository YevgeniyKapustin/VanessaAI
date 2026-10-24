from vanessa.knowledge.memory.writer import KnowledgeVaultWriter
from vanessa.knowledge.memory.writer_guards import (
    card_label,
    has_body,
    has_url,
    is_bare_url,
)
from vanessa.knowledge.memory.writer_recommendation import recommendation_target
from vanessa.knowledge.schema import MemoryPlan, VaultNote

_MENU = "https://lunch.example.com/menu"


class _Vault:
    is_configured = True

    def __init__(self) -> None:
        self.notes: dict[str, VaultNote] = {}

    async def read_note(self, relative_path: str) -> VaultNote | None:
        return self.notes.get(relative_path)

    async def write_note(self, relative_path, meta, body, mutation_source="") -> str:
        del mutation_source
        self.notes[relative_path] = VaultNote(relative_path, meta=meta, body=body)
        return relative_path


class _Index:
    def __init__(self) -> None:
        self.rebuilt: list[str] = []

    async def load_folder(self, folder: str) -> dict:
        del folder
        return {}

    async def rebuild_folder(self, folder: str) -> dict:
        self.rebuilt.append(folder)
        return {}


def test_url_guards() -> None:
    assert is_bare_url(_MENU)
    assert is_bare_url(f"  {_MENU} - ")
    assert is_bare_url("www.example.com/x")
    assert not is_bare_url("Blade Runner")
    assert not is_bare_url(f"Меню на пятницу {_MENU}")
    assert has_url(f"Меню {_MENU}")
    assert not has_url("Blade")
    assert card_label(_MENU) == ""
    assert card_label("  OSC ") == "OSC"
    assert card_label("") == ""
    assert has_body("## Описание\n- x")
    assert not has_body("  \n")


def test_recommendation_target_rejects_links() -> None:
    assert recommendation_target({"kind": "movies", "title": _MENU}) is None
    assert recommendation_target({"kind": "movies", "title": f"Обед {_MENU}"}) is None
    assert recommendation_target({"kind": "movies", "title": "Blade"}) is not None


async def test_writer_never_files_lunch_link_as_movie() -> None:
    vault, index = _Vault(), _Index()
    plan = MemoryPlan(
        updates=(
            {
                "type": "recommendation",
                "kind": "movies",
                "title": _MENU,
                "recommended_by": "Ada",
            },
            {
                "type": "recommendation",
                "kind": "movies",
                "title": _MENU,
                "description": "меню обедов на пятницу",
            },
        )
    )
    await KnowledgeVaultWriter(vault, index).apply(plan)
    assert vault.notes == {}


async def test_writer_skips_cards_without_body() -> None:
    vault = _Vault()
    plan = MemoryPlan(
        updates=(
            {"type": "recommendation", "kind": "movies", "title": "Blade"},
            {"type": "glossary", "term": "OSC"},
            {"type": "glossary", "term": _MENU, "definition": "lunch"},
            {"type": "event", "title": "Party"},
            {"type": "event", "title": _MENU, "summary": "lunch"},
        )
    )
    await KnowledgeVaultWriter(vault, _Index()).apply(plan)
    assert vault.notes == {}


async def test_writer_keeps_real_recommendation_and_existing_body() -> None:
    vault = _Vault()
    rel = "Culture/movies/blade.md"
    vault.notes[rel] = VaultNote(rel, meta={"status": "liked"}, body="## Описание\n- x")
    plan = MemoryPlan(
        updates=(
            {"type": "recommendation", "kind": "movies", "title": "Blade"},
            {
                "type": "recommendation",
                "kind": "games",
                "title": "Portal",
                "description": "puzzle game",
            },
        )
    )
    await KnowledgeVaultWriter(vault, _Index()).apply(plan)
    assert vault.notes[rel].meta["status"] == "liked"
    assert "puzzle game" in vault.notes["Culture/games/portal.md"].body
