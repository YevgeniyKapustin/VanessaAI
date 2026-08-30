"""SweepAnalyzer: periodic batch extraction over messages the bot never replied to.

The bot does not react to every message, so post-reply extraction alone would
miss most of the chat. A background worker polls the DB for messages newer than
a persisted cursor and, once ``interval_messages`` accumulate, chunks them into
context-window-sized windows and runs the memory decision per chunk. The cursor
lives in the vault's ``.state.yaml`` so a restart resumes where it left off.
"""

from __future__ import annotations

import asyncio
import logging

from vanessa.core.messages import StoredMessage, stored_to_context
from vanessa.knowledge.compaction import compact_all_person_cards
from vanessa.knowledge.memory_planner import MemoryPlanner
from vanessa.knowledge.memory_stage import format_memory_transcript
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.vault import KnowledgeVault
from vanessa.knowledge.writer import KnowledgeVaultWriter

logger = logging.getLogger(__name__)


def chunk_windows(
    messages: list,
    window_size: int,
    overlap: int,
) -> list[list]:
    """Split a batch into overlapping windows that fit the context window."""
    if not messages or window_size <= 0:
        return []
    step = max(1, window_size - max(0, overlap))
    windows: list[list] = []
    for start in range(0, len(messages), step):
        window = messages[start : start + window_size]
        if window:
            windows.append(window)
    return windows


class SweepAnalyzer:
    def __init__(
        self,
        vault: KnowledgeVault,
        planner: MemoryPlanner,
        writer: KnowledgeVaultWriter,
        *,
        interval_messages: int = 50,
        batch_size: int = 200,
        window_size: int = 40,
        window_overlap: int = 10,
        metrics: MetricsPipeline | None = None,
    ) -> None:
        self._vault = vault
        self._planner = planner
        self._writer = writer
        self._metrics = metrics
        self._interval = interval_messages
        self._batch = batch_size
        self._window = window_size
        self._overlap = window_overlap

    async def run(self, repo) -> int:
        """Fetch messages newer than the cursor; extract if threshold is reached.

        Returns the number of messages processed (0 when below threshold).
        """
        if not self._vault.is_configured:
            return 0
        cursor = await self._load_cursor()
        messages = await repo.get_newer_than(cursor, limit=self._batch)
        if len(messages) < self._interval:
            return 0
        processed = 0
        for window in chunk_windows(messages, self._window, self._overlap):
            transcript = self._transcript(window)
            try:
                plan = await self._planner.decide(transcript)
            except Exception:
                logger.exception("sweep_plan_failed window=%s messages", len(window))
                continue
            try:
                await self._writer.apply(
                    plan,
                    source_message_ids=[message.id for message in window],
                    mutation_source="sweep",
                )
            except Exception:
                logger.exception("sweep_apply_failed window=%s messages", len(window))
                continue
            processed += len(window)
        new_cursor = messages[-1].id
        await self._save_cursor(new_cursor)
        if self._metrics is not None:
            # No batch passed: the pipeline fetches the 14-day window itself
            # (all roles) so deterministic metrics are computed over the full
            # rolling window, not just the user-only sweep batch.
            try:
                await self._metrics.run(repo, semantic=True)
            except Exception:
                logger.exception("sweep_metrics_failed")
        # Keep person context bounded: compact (sort + time-bucket + archive)
        # after each batch so «Контекст жизни» never grows without bound.
        try:
            await compact_all_person_cards(self._vault)
        except Exception:
            logger.exception("sweep_compaction_failed")
        logger.info(
            "sweep_done fetched=%s processed=%s cursor=%s",
            len(messages),
            processed,
            new_cursor,
        )
        return processed

    async def _load_cursor(self) -> int:
        state = await self._vault.read_state()
        try:
            return int(state.get("last_message_id", 0))
        except (TypeError, ValueError):
            return 0

    async def _save_cursor(self, message_id: int) -> None:
        await self._vault.write_state({"last_message_id": message_id})

    @staticmethod
    def _transcript(messages: list[StoredMessage]) -> str:
        context = [stored_to_context(message) for message in messages]
        # Canonicalize sender labels (roster nicknames + telegram ids), exactly
        # like the post-reply MemoryStage, so the memory LLM never sees raw
        # Telegram display names («Yevgeniy») that become duplicate person cards.
        return format_memory_transcript(context)


class SweepWorker:
    """Background loop that periodically checks whether a sweep is due."""

    def __init__(
        self,
        sweep: SweepAnalyzer,
        session_factory,
        *,
        poll_seconds: int = 60,
    ) -> None:
        self._sweep = sweep
        self._session_factory = session_factory
        self._poll = poll_seconds

    async def run_forever(self) -> None:
        while True:
            try:
                async with self._session_factory() as session:
                    from vanessa.infrastructure.db.repository import MessageRepository

                    processed = await self._sweep.run(MessageRepository(session))
                    if processed:
                        logger.info("sweep_worker processed=%s", processed)
            except Exception:
                logger.exception("sweep_worker_cycle_failed")
            await asyncio.sleep(self._poll)
