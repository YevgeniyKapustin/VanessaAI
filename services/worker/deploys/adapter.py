"""Map the deploy bridge payload to the generic announcement shape.

This is the whole deploy-specific part of the engine: the HTTP source is
shared, and everything after parsing — dedupe, readiness, wording, posting —
does not know what a deploy is.
"""

from __future__ import annotations

import logging

from services.worker.announce.models import Actor, Announcement, Item
from services.worker.deploys.models import DeployEvent
from services.worker.deploys.release import event_release

logger = logging.getLogger(__name__)


def deploy_announcement(payload: dict) -> Announcement | None:
    """The newest successful production deploy, or None when unknown."""
    deploy = payload.get("deploy")
    if not deploy:
        return None
    try:
        event = DeployEvent.model_validate(deploy)
    except ValueError:
        logger.warning("deploy_bridge_bad_payload")
        return None
    person = event.started_by or event.runner
    return Announcement(
        key=event.job_id,
        when=event.finished_at,
        url=(event.pipeline.web_url or event.web_url).strip(),
        actor=Actor(name=person.name, username=person.username) if person else None,
        items=tuple(
            Item(title=commit.title, author=commit.author_name)
            for commit in event.commits
        ),
        total=event.total_commits,
        release=event_release(event),
    )


__all__ = ["deploy_announcement"]
