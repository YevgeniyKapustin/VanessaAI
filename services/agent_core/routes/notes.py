"""Owner inbox notes — written by agent-core, not the bot process."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.agent_core.auth import verify_internal_token
from vanessa.knowledge.format import INBOX, TYPE_NOTE, today
from vanessa.knowledge.vault import KnowledgeVault

router = APIRouter(dependencies=[Depends(verify_internal_token)])


class InboxNoteRequest(BaseModel):
    text: str = ""
    attachment_base64: str | None = None
    attachment_suffix: str = Field(default=".jpg", max_length=16)


class InboxNoteResponse(BaseModel):
    path: str


@router.post("/notes", response_model=InboxNoteResponse)
async def create_inbox_note(body: InboxNoteRequest) -> InboxNoteResponse:
    vault = KnowledgeVault()
    if not vault.is_configured:
        raise HTTPException(status_code=503, detail="knowledge_not_configured")
    text = body.text.strip()
    attachment_bytes: bytes | None = None
    if body.attachment_base64:
        try:
            attachment_bytes = base64.b64decode(body.attachment_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="bad_attachment") from exc
    if not text and not attachment_bytes:
        raise HTTPException(status_code=400, detail="empty_note")
    await vault.ensure_structure()
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d_%H%M%S")
    note_path = f"{INBOX}/{stamp}.md"
    body_parts: list[str] = []
    if text:
        body_parts.append(text)
    if attachment_bytes:
        suffix = body.attachment_suffix
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        attachment_rel = f"{INBOX}/attachments/{stamp}{suffix}"
        await vault.write_attachment(attachment_rel, attachment_bytes)
        body_parts.append(f"![[{attachment_rel}]]")
    saved = await vault.write_note(
        note_path,
        {"type": TYPE_NOTE, "date": today(), "tags": [INBOX]},
        "\n\n".join(body_parts),
    )
    return InboxNoteResponse(path=saved)
