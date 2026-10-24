"""Loop limits for talk with other AI bots (Bot-to-Bot Communication Mode)."""

from __future__ import annotations


class BotPeerMixin:
    """Agent settings for replies to other Telegram bots. 0 turns a limit off."""

    # Replies in a row to one peer bot in a chat; a person's message resets it.
    decision_bot_peer_max_in_row: int = 3
    # Seconds between two replies to the same peer bot (a sooner message is
    # skipped, not delayed).
    decision_bot_peer_cooldown_seconds: float = 10.0
    # Replies to bots per chat in a sliding hour.
    decision_bot_peer_max_per_hour: int = 20
