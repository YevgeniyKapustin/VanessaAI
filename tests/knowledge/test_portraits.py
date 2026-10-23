from unittest.mock import AsyncMock

from vanessa.knowledge.portraits import PortraitBuilder
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.vault import KnowledgeVault


async def _vault(tmp_path) -> KnowledgeVault:
    vault = KnowledgeVault(store=FilesystemKnowledgeStore(str(tmp_path)))
    await vault.ensure_structure()
    await vault.write_note(
        "People/ada.md",
        {"id": "ada", "type": "person", "telegram_id": 7},
        "## Контекст жизни\n- любит чай",
    )
    await vault.write_note(
        "People/team.md",
        {"id": "team", "type": "person", "nickname": "Команда"},
        "## Состав\n- Ада — тимлид",
    )
    return vault


async def test_portraits_only_for_cards_with_telegram_id(tmp_path) -> None:
    vault = await _vault(tmp_path)
    planner = AsyncMock()
    planner.portrait.return_value = "Ада любит чай."
    builder = PortraitBuilder(vault, planner, enabled=True, max_chars=1000)

    assert await builder.run() == 1

    ada = await vault.read_note("People/ada.md")
    team = await vault.read_note("People/team.md")
    assert ada.meta["portrait"] == "Ада любит чай."
    assert "portrait" not in team.meta
    planner.portrait.assert_awaited_once()
    assert await builder.run() == 0
