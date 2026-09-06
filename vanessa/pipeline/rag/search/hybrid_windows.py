import logging
import time

from vanessa.config import settings
from vanessa.core.messages import RAG_SOURCE_ROLE, ContextBlock, stored_block_to_context
from vanessa.core.protocols import MessageRepositoryProtocol
from vanessa.infrastructure.observability.metrics import record_rag_search

logger = logging.getLogger("vanessa.pipeline.rag.search.hybrid_search")


def effective_window_max_total(anchor_max: int | None = None) -> int:
    anchors = anchor_max or settings.rag_anchor_max
    per_window = (
        settings.rag_context_window_before
        + 1
        + settings.rag_context_window_after
    )
    return max(settings.rag_context_window_max_total, anchors * per_window)


async def load_window_context_blocks(
    messages: MessageRepositoryProtocol,
    selected_ids: list[int],
    *,
    before: int,
    after: int,
    max_total: int,
) -> list[ContextBlock]:
    raw_blocks = await messages.get_conversation_window_blocks(
        anchor_ids=selected_ids,
        before=before,
        after=after,
        max_total=max_total,
    )
    return [
        block
        for anchor_id, window_messages in raw_blocks
        if (block := stored_block_to_context(anchor_id, window_messages)) is not None
    ]


async def load_selected_context_blocks(
    messages: MessageRepositoryProtocol,
    query: str,
    selected_ids: list[int],
    *,
    window_before: int | None,
    window_after: int | None,
    anchor_max: int | None,
    vector_ms: float,
    fts_ms: float,
    top_score: float,
) -> list[ContextBlock]:
    before = (
        window_before
        if window_before is not None
        else settings.rag_context_window_before
    )
    after = (
        window_after
        if window_after is not None
        else settings.rag_context_window_after
    )
    max_total = effective_window_max_total(anchor_max)
    window_started = time.perf_counter()
    if before > 0 or after > 0:
        blocks = await load_window_context_blocks(
            messages,
            selected_ids,
            before=before,
            after=after,
            max_total=max_total,
        )
        message_count = sum(len(block.messages) for block in blocks)
        window_ms = (time.perf_counter() - window_started) * 1000
        logger.info(
            "rag_context_expanded query=%r anchors=%s blocks=%s messages=%s "
            "vector_ms=%.1f fts_ms=%.1f window_ms=%.1f",
            query,
            len(selected_ids),
            len(blocks),
            message_count,
            vector_ms,
            fts_ms,
            window_ms,
        )
        record_rag_search("raw", hits=len(blocks), top_score=top_score)
        return blocks

    stored = await messages.get_by_ids(selected_ids)
    user_messages = [
        message for message in stored if message.role == RAG_SOURCE_ROLE
    ]
    window_ms = (time.perf_counter() - window_started) * 1000
    logger.info(
        "rag_search_done query=%r anchors=%s vector_ms=%.1f fts_ms=%.1f "
        "window_ms=%.1f",
        query,
        len(user_messages),
        vector_ms,
        fts_ms,
        window_ms,
    )
    record_rag_search("raw", hits=len(user_messages), top_score=top_score)
    return [
        block
        for message in user_messages
        if (block := stored_block_to_context(message.id, [message])) is not None
    ]
