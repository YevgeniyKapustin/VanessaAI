"""The release label a deploy announcement puts in its header.

A deploy that carries a tag is a release: the header is that tag alone. Any
other deploy rides on the newest tag, so the header names the tag and then the
deploy number in parentheses — «v0.1.6 (79545)» — and the reader can tell the
two apart without opening the pipeline.
"""

from __future__ import annotations

from services.worker.deploys.models import DeployEvent


def release_label(*, tag: str, latest_tag: str, number: str) -> str:
    """«v0.1.7» for a tagged release, «v0.1.6 (79545)» between releases."""
    tag = (tag or "").strip()
    if tag:
        return tag
    latest = (latest_tag or "").strip()
    number = (number or "").strip()
    if latest and number:
        return f"{latest} ({number})"
    return latest or number


def event_release(event: DeployEvent) -> str:
    """The label for one bridge event; the pipeline id is the deploy number."""
    number = str(event.pipeline.id or event.job_id or "")
    return release_label(tag=event.tag, latest_tag=event.latest_tag, number=number)


__all__ = ["event_release", "release_label"]
