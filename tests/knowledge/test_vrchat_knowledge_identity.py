from vanessa.knowledge.format import PEOPLE
from vanessa.knowledge.index.index import KnowledgeIndex
from vanessa.knowledge.memory.writer import KnowledgeVaultWriter
from vanessa.knowledge.metrics.retriever import MetricsRetriever
from vanessa.knowledge.schema import MemoryPlan
from vanessa.knowledge.store.store_fs import FilesystemKnowledgeStore
from vanessa.knowledge.store.vault import KnowledgeVault
from vanessa.knowledge.users.alias_extract import (
    aliases_from_notes,
    telegram_nicknames_from_notes,
)


async def test_vrchat_memory_and_metrics_use_existing_telegram_card(tmp_path):
    vault = KnowledgeVault(store=FilesystemKnowledgeStore(str(tmp_path)))
    telegram_id = 42
    await vault.write_note(
        "People/owner.md",
        {
            "type": "person",
            "id": "owner",
            "nickname": "Евгений",
            "telegram_id": telegram_id,
            "vrchat_names": ["Yevgeniy"],
            "metrics": {"trust_score": 80},
        },
        "## Контекст жизни\n",
    )
    index = KnowledgeIndex(vault)
    await index.rebuild_folder(PEOPLE)
    writer = KnowledgeVaultWriter(vault, index)
    await writer.apply(
        MemoryPlan(updates=(
            {
                "type": "person_fact",
                "person": "Yevgeniy",
                "channel": "vrchat",
                "text": "Проверяет VRChat.",
            },
        )),
    )
    notes = await vault.list_notes(PEOPLE)
    assert len(notes) == 1
    assert notes[0].note_id == "owner"
    assert notes[0].meta["telegram_id"] == telegram_id
    assert notes[0].meta["vrchat_names"] == ["Yevgeniy"]
    assert "Проверяет VRChat." in notes[0].body
    assert aliases_from_notes(notes)["Евгений"] == ("Yevgeniy",)
    assert telegram_nicknames_from_notes(notes) == {telegram_id: "Евгений"}
    retriever = MetricsRetriever(vault, index)
    vrchat = await retriever.get_by_vrchat_name("Yevgeniy")
    telegram = await retriever.get_by_telegram_id(telegram_id)
    assert vrchat == telegram
