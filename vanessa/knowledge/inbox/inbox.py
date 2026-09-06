from __future__ import annotations

import base64
from datetime import UTC, datetime

from vanessa.knowledge.format import INBOX, TYPE_NOTE, today
from vanessa.knowledge.store.vault import KnowledgeVault


class InboxNoteError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _decode_attachment(attachment_base64: str | None) -> bytes | None:
    if not attachment_base64:
        return None
    try:
        return base64.b64decode(attachment_base64)
    except Exception as exc:
        raise InboxNoteError("bad_attachment") from exc


def _require_inbox_payload(body_text: str, attachment_bytes: bytes | None) -> None:
    if body_text or attachment_bytes:
        return
    raise InboxNoteError("empty_note")


def _dotted_suffix(attachment_suffix: str) -> str:
    if attachment_suffix.startswith("."):
        return attachment_suffix
    return f".{attachment_suffix}"


async def _write_inbox_embed(
    vault: KnowledgeVault,
    stamp: str,
    attachment_bytes: bytes | None,
    attachment_suffix: str,
) -> str | None:
    if not attachment_bytes:
        return None
    suffix = _dotted_suffix(attachment_suffix)
    attachment_rel = f"{INBOX}/attachments/{stamp}{suffix}"
    await vault.write_attachment(attachment_rel, attachment_bytes)
    return f"![[{attachment_rel}]]"


def _inbox_body(body_text: str, embed: str | None) -> str:
    parts: list[str] = []
    if body_text:
        parts.append(body_text)
    if embed:
        parts.append(embed)
    return "\n\n".join(parts)


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
    attachment_bytes = _decode_attachment(attachment_base64)
    _require_inbox_payload(body_text, attachment_bytes)
    await vault.ensure_structure()
    stamp = datetime.now(UTC).astimezone().strftime("%Y-%m-%d_%H%M%S")
    note_path = f"{INBOX}/{stamp}.md"
    embed = await _write_inbox_embed(
        vault, stamp, attachment_bytes, attachment_suffix
    )
    return await vault.write_note(
        note_path,
        {"type": TYPE_NOTE, "date": today(), "tags": [INBOX]},
        _inbox_body(body_text, embed),
    )
