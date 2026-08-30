from __future__ import annotations

from enum import Enum

from vanessa.config.settings import settings


class ProcessRole(Enum):
    """How this agent process shares work with the worker.

    INLINE: no worker — run knowledge loops and turn side-effects here.
    DISPATCH: worker is up — publish tasks, skip in-process loops.
    """

    INLINE = "inline"
    DISPATCH = "dispatch"

    @classmethod
    def from_settings(cls, *, worker_enabled: bool | None = None) -> ProcessRole:
        split = (
            settings.worker_enabled if worker_enabled is None else worker_enabled
        )
        return cls.DISPATCH if split else cls.INLINE

    @property
    def owns_knowledge_loops(self) -> bool:
        return self is ProcessRole.INLINE

    @property
    def dispatches_tasks(self) -> bool:
        return self is ProcessRole.DISPATCH

    @property
    def inline_turn_effects(self) -> bool:
        return self is ProcessRole.INLINE
