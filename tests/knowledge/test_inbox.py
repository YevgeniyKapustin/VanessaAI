import pytest

from vanessa.knowledge.inbox import InboxNoteError, save_inbox_note


class _Vault:
    def __init__(self, configured: bool = True) -> None:
        self.is_configured = configured
        self.notes: list[tuple[str, dict, str]] = []
        self.attachments: list[tuple[str, bytes]] = []

    async def ensure_structure(self) -> None:
        return None

    async def write_attachment(self, relative_path: str, data: bytes) -> str:
        self.attachments.append((relative_path, data))
        return relative_path

    async def write_note(self, relative_path: str, meta: dict, body: str) -> str:
        self.notes.append((relative_path, meta, body))
        return relative_path


async def test_save_inbox_note_writes_text() -> None:
    vault = _Vault()
    path = await save_inbox_note(vault, text="buy milk")
    assert path.startswith("inbox/")
    assert path.endswith(".md")
    assert vault.notes[0][2] == "buy milk"


async def test_save_inbox_note_rejects_empty() -> None:
    with pytest.raises(InboxNoteError) as exc:
        await save_inbox_note(_Vault(), text="  ")
    assert exc.value.code == "empty_note"


async def test_save_inbox_note_requires_vault() -> None:
    with pytest.raises(InboxNoteError) as exc:
        await save_inbox_note(_Vault(configured=False), text="hi")
    assert exc.value.code == "knowledge_not_configured"
