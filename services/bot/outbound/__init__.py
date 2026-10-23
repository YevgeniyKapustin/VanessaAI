"""Late follow-ups (worker → bot) posted from the ``outbound`` stream."""

from services.bot.outbound.consumer import (
    OUTBOUND_GROUP,
    handle_outbound,
    run_outbound_loop,
    start_outbound_task,
)
from services.bot.outbound.send import post_outbound

__all__ = [
    "OUTBOUND_GROUP",
    "handle_outbound",
    "post_outbound",
    "run_outbound_loop",
    "start_outbound_task",
]
