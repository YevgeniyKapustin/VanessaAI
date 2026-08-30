from __future__ import annotations

import base64
from datetime import UTC, datetime

from vanessa.knowledge.format import INBOX, TYPE_NOTE, today
from vanessa.knowledge.vault import KnowledgeVault


class InboxNoteError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def save_inbox_note(
    vault: KnowledgeVault,
    *,
    text: str = "",
    attachment_base64: str | None = None,
    attachment_suffix: str = ".jpg",
) -> str:
    if not vault.is_configured:
        raise InboxNoteError("knowledge_not_configured")
    body_text = text.strip()
    attachment_bytes: bytes | None = None
    if attachment_base64:
        try:
            attachment_bytes = base64.b64decode(attachment_base64)
        except Exception as exc:
            raise InboxNoteError("bad_attachment") from exc
    if not body_text and not attachment_bytes:
        raise InboxNoteError("empty_note")
    await vault.ensure_structure()
    stamp = datetime.now(UTC).astimezone().strftime("%Y-%m-%d_%H%M%S")
    note_path = f"{INBOX}/{stamp}.md"
    parts: list[str] = []
    if body_text:
        parts.append(body_text)
    if attachment_bytes:
        suffix = attachment_suffix
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        attachment_rel = f"{INBOX}/attachments/{stamp}{suffix}"
        await vault.write_attachment(attachment_rel, attachment_bytes)
        parts.append(f"![[{attachment_rel}]]")
    return await vault.write_note(
        note_path,
        {"type": TYPE_NOTE, "date": today(), "tags": [INBOX]},
        "\n\n".join(parts),
    )
