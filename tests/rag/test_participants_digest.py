import pytest

from app.knowledge.format import PEOPLE
from app.knowledge.index import KnowledgeIndex
from app.knowledge.participants import ParticipantsDigest
from app.knowledge.vault import KnowledgeVault


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
        "- 2026-08-26: Местный философ.\n"
        "- 2026-08-26: Устроился сварщиком.\n"
        "- 2026-08-26: Играет в ХСР.\n",
    )
    await vault.write_note(
        "People/крабер.md",
        {
            "type": "person",
            "id": "крабер",
            "aliases": ["Крабер"],
            "mood": "подкалывает",
        },
        "## Контекст жизни\n\n- 2026-08-26: Любит пещеры.\n",
    )
    index = KnowledgeIndex(vault)
    await index.rebuild_folder(PEOPLE)
    return vault


@pytest.mark.asyncio
async def test_build_returns_per_person_lines(tmp_path):
    vault = await _seed_vault(tmp_path)
    digest = ParticipantsDigest(vault, max_people=20, max_facts=5)

    text = await digest.build()

    assert "крабер" in text
    assert "настроение: подкалывает" in text
    assert "Любит пещеры" in text
    assert "личь" in text
    assert "настроение: согласный" in text
    # Only the most recent facts are kept (newest last, capped by max_facts).
    assert "Играет в ХСР" in text


@pytest.mark.asyncio
async def test_max_facts_caps_recent_facts(tmp_path):
    vault = await _seed_vault(tmp_path)
    digest = ParticipantsDigest(vault, max_people=20, max_facts=1)

    text = await digest.build()

    # Only the last fact for Личь survives.
    assert "Играет в ХСР" in text
    assert "Местный философ" not in text


@pytest.mark.asyncio
async def test_cache_invalidates_on_note_edit(tmp_path):
    vault = await _seed_vault(tmp_path)
    digest = ParticipantsDigest(vault, max_people=20, max_facts=5)

    first = await digest.build()
    assert "новый факт" not in first

    # Edit a note body (changes size -> invalidates the digest cache).
    note = await vault.read_note("People/личь.md")
    body = note.body + "- 2026-08-26: Новый факт про работу.\n"
    await vault.write_note("People/личь.md", note.meta, body)

    second = await digest.build()
    assert "Новый факт про работу" in second
