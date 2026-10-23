"""Wire models for the Hermes Agent runs API."""

from __future__ import annotations

from dataclasses import dataclass

# Terminal run statuses (Hermes API server docs, "Runs API").
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


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


class HermesUnavailableError(RuntimeError):
    """Hermes is offline (PC off, tunnel down) or refused the run."""
