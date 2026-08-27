import pytest

from app.knowledge.portraits import PortraitBuilder, PortraitPlanner
from app.knowledge.vault import KnowledgeVault


class FakePlanner:
    def __init__(self, result: str = "Личь — философ и сварщик.") -> None:
        self.result = result
        self.calls = 0
        self.last: dict = {}

    async def portrait(self, *, nickname, aliases, mood, dossier):
        self.calls += 1
        self.last = {
            "nickname": nickname,
            "aliases": aliases,
            "mood": mood,
            "dossier": dossier,
        }
        return self.result


async def _seed_vault(tmp_path) -> KnowledgeVault:
    vault = KnowledgeVault(str(tmp_path))
    await vault.write_note(
        "People/личь.md",
        {
            "type": "person",
            "id": "личь",
            "aliases": ["Личь"],
            "mood": "согласный",
        },
        "## Контекст жизни\n\n"
        "- 2026-08-26: Философ.\n"
        "- 2026-08-26: Устроился сварщиком.\n",
    )
    return vault


@pytest.mark.asyncio
async def test_builder_writes_portrait_and_skips_unchanged(tmp_path):
    vault = await _seed_vault(tmp_path)
    planner = FakePlanner()
    builder = PortraitBuilder(vault, planner, enabled=True)

    updated = await builder.run()
    assert updated == 1
    assert planner.calls == 1

    note = await vault.read_note("People/личь.md")
    assert note.meta.get("portrait") == planner.result
    assert note.meta.get("portrait_signature")
    # The raw dossier body is preserved (needed for on-demand fact questions).
    assert "Устроился сварщиком" in note.body

    # Unchanged dossier -> no regeneration on the next pass.
    assert await builder.run() == 0
    assert planner.calls == 1


@pytest.mark.asyncio
async def test_builder_regenerates_when_dossier_changes(tmp_path):
    vault = await _seed_vault(tmp_path)
    planner = FakePlanner()
    builder = PortraitBuilder(vault, planner, enabled=True)

    assert await builder.run() == 1

    note = await vault.read_note("People/личь.md")
    await vault.write_note(
        "People/личь.md",
        note.meta,
        note.body + "- 2026-08-26: Переехал в Грузию.\n",
    )
    assert await builder.run() == 1
    assert planner.calls == 2


@pytest.mark.asyncio
async def test_builder_force_rebuilds_everything(tmp_path):
    vault = await _seed_vault(tmp_path)
    planner = FakePlanner()
    builder = PortraitBuilder(vault, planner, enabled=True)

    assert await builder.run() == 1
    assert await builder.run(force=True) == 1
    assert planner.calls == 2


@pytest.mark.asyncio
async def test_builder_disabled_returns_zero(tmp_path):
    vault = await _seed_vault(tmp_path)
    builder = PortraitBuilder(vault, FakePlanner(), enabled=False)
    assert await builder.run() == 0


@pytest.mark.asyncio
async def test_planner_formats_prompt_and_returns_clean_portrait():
    class FakeCompleter:
        def __init__(self) -> None:
            self.prompt = ""

        async def complete(self, model, messages, *, kind, **kwargs):
            self.prompt = messages[0]["content"]
            return (
                "  Крабер — отшельник из Екатеринбурга.\n"
                "Готовит и критикует общество.  "
            )

    completer = FakeCompleter()
    planner = PortraitPlanner(llm_client=completer, llm_model="test-model")

    result = await planner.portrait(
        nickname="крабер",
        aliases=["Крабер"],
        mood="подкалывает",
        dossier="тело досье",
    )

    assert "крабер" in completer.prompt
    assert "тело досье" in completer.prompt
    # Newlines are collapsed and no stray whitespace survives.
    assert "\n" not in result
    assert "отшельник из Екатеринбурга" in result


@pytest.mark.asyncio
async def test_planner_strips_markdown_fence():
    class FakeCompleter:
        async def complete(self, model, messages, *, kind, **kwargs):
            return "```text\nПортрет без рамок.\n```"

    planner = PortraitPlanner(llm_client=FakeCompleter(), llm_model="test-model")
    result = await planner.portrait(
        nickname="x",
        aliases=[],
        mood="",
        dossier="тело",
    )
    assert result == "Портрет без рамок."
