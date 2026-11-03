"""Wire model of the PC deploy bridge (a read-only view of GitLab).

The bridge answers with the newest successful ``deploy:production`` job and
the commits between it and the previous one, so the server never talks to
the internal GitLab itself (that host refuses datacenter IPs).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DeployPerson(BaseModel):
    username: str = ""
    name: str = ""

    def label(self) -> str:
        """«Вячеслав Титов (@v.titov)», or whichever half exists."""
        name = self.name.strip()
        handle = f"@{self.username}" if self.username else ""
        if name and handle:
            return f"{name} ({handle})"
        return name or handle or "неизвестно"


class DeployCommit(BaseModel):
    short_id: str = ""
    title: str = ""
    author_name: str = ""


class DeployPipeline(BaseModel):
    id: int = 0
    sha: str = ""
    web_url: str = ""


class DeployEvent(BaseModel):
    """One successful production deploy, as the bridge reports it."""

    job_id: int
    finished_at: datetime | None = None
    web_url: str = ""
    pipeline: DeployPipeline = Field(default_factory=DeployPipeline)
    #: Who pressed the rollout (``deploy:production:start``).
    started_by: DeployPerson | None = None
    #: Who ran the deploy job itself.
    runner: DeployPerson | None = None
    commits: list[DeployCommit] = Field(default_factory=list)
    #: Commits in the whole release, including the ones not listed above.
    commit_total: int = 0

    @property
    def started_by_label(self) -> str:
        return (self.started_by or self.runner or DeployPerson()).label()

    @property
    def total_commits(self) -> int:
        return max(self.commit_total, len(self.commits))


__all__ = [
    "DeployCommit",
    "DeployEvent",
    "DeployPerson",
    "DeployPipeline",
]
