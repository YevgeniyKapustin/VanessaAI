"""Compose directive for the Hermes ask (the owner's PC agent).

The Retrieve stage sets ``hermes_status``: "asked" (a worker task is queued,
Hermes answers later in a separate message), "offline" (the PC is off,
nothing is queued), "answered" (a result posted lately already answers it,
nothing is queued) or None (no lookup this turn). Every status gets a note,
so compose always knows whether a later result can come. The text lives in
``config/behavior/compose/notes.yaml``.
"""

from vanessa.config.content import AppContent
from vanessa.core.generate_request import GenerateRequest
from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, BudgetPart


def _hermes_note(content: AppContent, hermes_status: str | None) -> str:
    llm = content.llm
    notes = {
        "asked": llm.hermes_asked_note,
        "offline": llm.hermes_offline_note,
        "answered": llm.hermes_answered_note,
    }
    return notes.get(hermes_status or "", llm.hermes_none_note).strip()


def _retry_note(content: AppContent, request: GenerateRequest) -> str:
    if not request.false_promise_retry:
        return ""
    return content.llm.false_promise_retry_note.strip()


def hermes_parts(content: AppContent, request: GenerateRequest) -> list[BudgetPart]:
    notes = (
        _hermes_note(content, request.hermes_status),
        _retry_note(content, request),
    )
    return [(PRIORITY_DIRECTIVES, "directives", note) for note in notes if note]
