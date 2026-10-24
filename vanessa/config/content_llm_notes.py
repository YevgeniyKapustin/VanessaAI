"""Compose notes about work lookups, retries and the earlier-thread block.

Text lives in ``config/behavior/compose/notes.yaml`` and ``layout.yaml``.
"""

from pydantic import BaseModel


class LLMLookupNotes(BaseModel):
    # Hermes ask directives (TurnPlan.ask_hermes): task queued / PC offline /
    # result already posted / no lookup this turn (then she must not promise
    # a later result).
    hermes_asked_note: str = ""
    hermes_offline_note: str = ""
    hermes_answered_note: str = ""
    hermes_none_note: str = ""
    # Retry note when a reply promised a later result with no lookup running.
    false_promise_retry_note: str = ""
    # Untagged output: the strict note for the retry, the line for a direct ask.
    untagged_retry_note: str = ""
    untagged_fallback: str = ""
    # Messages before the idle gap (an older thread of the same chat).
    earlier_header: str = "<!-- Earlier in the chat, before a pause -->"
