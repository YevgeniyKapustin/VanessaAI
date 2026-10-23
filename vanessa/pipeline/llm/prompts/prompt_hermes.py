"""Compose directive for the Hermes ask (the owner's PC agent).

The Retrieve stage sets ``hermes_status``: "asked" (a worker task is queued,
Hermes answers later in a separate message) or "offline" (the PC is off,
nothing is queued). The text lives in ``config/behavior/compose/notes.yaml``.
"""

from vanessa.config.content import AppContent
from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, BudgetPart


def _hermes_note(content: AppContent, hermes_status: str | None) -> str:
    llm = content.llm
    if hermes_status == "asked":
        return llm.hermes_asked_note.strip()
    if hermes_status == "offline":
        return llm.hermes_offline_note.strip()
    return ""


def hermes_parts(content: AppContent, hermes_status: str | None) -> list[BudgetPart]:
    note = _hermes_note(content, hermes_status)
    if not note:
        return []
    return [(PRIORITY_DIRECTIVES, "directives", note)]
