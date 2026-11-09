"""Wire models for the Hermes Agent runs API."""

from __future__ import annotations

from dataclasses import dataclass

# Terminal run statuses (Hermes API server docs, "Runs API").
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})

#: Why a run ended without an answer. Codes, not prose: the worker maps one
#: to a line in the chat through ``failure_meanings`` (followup.yaml).
FAILURE_BLOCKED = "blocked"  # the run asked for approval or a clarification
FAILURE_TIMEOUT = "timeout"  # past ``max_wait_seconds``, stopped by us
FAILURE_INTERRUPTED = "interrupted"  # cancelled or interrupted on Hermes' side
FAILURE_FAILED = "failed"  # the run itself errored
FAILURE_EMPTY = "empty"  # finished with nothing usable


@dataclass(frozen=True)
class HermesRun:
    run_id: str
    status: str
    output: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def needs_human(self) -> bool:
        # ``waiting_for_approval`` / clarify prompts: nobody can answer them
        # from a group chat, so the poller stops the run (deny-and-stop).
        return self.status.startswith("waiting")

    @property
    def failure(self) -> str:
        """Why this run has no answer; empty when it delivered one."""
        if self.is_completed:
            return "" if self.output else FAILURE_EMPTY
        return terminal_failure(self.status)


def terminal_failure(status: str) -> str:
    """The reason code for a run that ended without an answer."""
    if status.startswith("waiting"):
        return FAILURE_BLOCKED
    if status in ("cancelled", "interrupted"):
        return FAILURE_INTERRUPTED
    return FAILURE_FAILED


class HermesUnavailableError(RuntimeError):
    """Hermes is offline (PC off, tunnel down) or refused the run."""
