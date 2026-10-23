"""Pinned-notes retrieve step: notes Vanessa sees on every reply."""

from __future__ import annotations

import logging

from vanessa.core.protocols import PinnedNotesProtocol
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger("vanessa.pipeline.stages")


async def run_pinned_step(
    ctx: TurnPipelineContext,
    pinned: PinnedNotesProtocol | None,
) -> None:
    """Add the pinned notes to the compose knowledge blocks. Fails open."""
    if pinned is None:
        return
    try:
        blocks = await pinned.blocks()
    except Exception:
        logger.exception("pinned_notes_failed request_id=%s", get_request_id())
        return
    ctx.knowledge_blocks.extend(blocks)
