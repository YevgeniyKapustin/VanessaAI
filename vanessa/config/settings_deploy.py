"""Settings for production-deploy announcements.

The GitLab side lives on the owner's PC (``deploy/vanessa-bridge``): the
server cannot reach the internal GitLab directly. The worker asks that
bridge for the latest ``deploy:production`` job and posts one message when
a new one succeeded.

Nothing here names a real host or chat: the stand probe, the chat id and
the rollout dashboard come from ``.env.local``, so the repository stays
free of production identifiers.
"""

from __future__ import annotations


class DeployWatchMixin:
    """Watching the production lane and announcing it in the chat."""

    deploy_watch_enabled: bool = False
    # Read-only bridge on the PC, reached through the reverse SSH tunnel.
    deploy_bridge_url: str = ""
    deploy_bridge_token: str = ""
    # The chat the announcement goes to.
    deploy_chat_id: int = 0
    # The worker asks the bridge this often.
    deploy_poll_seconds: float = 60.0
    # A deploy older than this (worker was down) is remembered, not posted.
    deploy_max_late_hours: int = 12
    # Wait for the stand to answer before posting; 0 skips the wait.
    deploy_ready_timeout_seconds: int = 900
    deploy_ready_poll_seconds: float = 30.0
    # Public stand origin; empty disables the readiness wait.
    deploy_probe_url: str = ""
    # Prod tenant-rollout dashboard, linked under the bullets; empty hides it.
    # Set it in .env.local with `$$__all`: an `--env-file` value is itself
    # interpolated, so a single `$` disappears. A Python default cannot be
    # used for a real URL without naming production here.
    deploy_rollout_url: str = ""
    # Card page for every card named in the разбор: a URL template with
    # `{card}` («…/browse/{card}/»), so the commit tag links to its own card.
    # Empty keeps the ids as plain text; no default for the same reason.
    deploy_card_url: str = ""
