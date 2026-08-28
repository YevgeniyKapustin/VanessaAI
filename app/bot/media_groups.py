"""Media-group (album) aggregation for the Telegram bot.

Telegram sends every photo of an album as a SEPARATE message, all sharing the
same ``media_group_id``. If each photo were processed as its own turn, the bot
would answer after the first one — e.g. "сравни картины" with only a single
painting in view. ``MediaGroupBuffer`` accumulates the photos of a media group
and flushes them as ONE aggregated turn once the group has been quiet for a
short debounce window (restarted on every arrival), so the vision model sees the
whole album at once.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aiogram.types import Message as TelegramMessage

from app.config.settings import settings
from app.core.messages import ImageAttachment

logger = logging.getLogger(__name__)

# The flush callback receives the aggregated entry: it builds the combined
# ``IncomingMessage`` (primary caption + all images) and runs the turn pipeline.
MediaGroupFlushCallback = Callable[["MediaGroupEntry"], Awaitable[None]]


@dataclass(slots=True)
class MediaGroupEntry:
    """Accumulated state of one media group pending its flush."""

    chat_id: int
    media_group_id: str
    on_flush: MediaGroupFlushCallback
    images: list[ImageAttachment] = field(default_factory=list)
    messages: list[TelegramMessage] = field(default_factory=list)
    task: asyncio.Task | None = None


class MediaGroupBuffer:
    """Buffer an album's photos and flush them as one turn after a debounce.

    Thread-safety: the shared group dict is guarded by an asyncio lock. The
    debounce timer is a per-group task that is cancelled and re-created on every
    photo of the group, so the flush only fires after the group goes quiet.
    """

    def __init__(
        self,
        *,
        debounce_seconds: float | None = None,
        max_photos: int | None = None,
    ) -> None:
        self._debounce_seconds = (
            settings.vision_media_group_debounce_seconds
            if debounce_seconds is None
            else debounce_seconds
        )
        self._max_photos = (
            settings.vision_media_group_max_photos
            if max_photos is None
            else max_photos
        )
        self._groups: dict[tuple[int, str], MediaGroupEntry] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        chat_id: int,
        media_group_id: str,
        message: TelegramMessage,
        images: list[ImageAttachment],
        on_flush: MediaGroupFlushCallback,
    ) -> bool:
        """Buffer one photo of a media group.

        Returns True (the caller must not process the message itself — the group
        will be flushed as one turn). When the group reaches ``max_photos`` it is
        flushed immediately instead of waiting out the debounce.
        """
        key = (chat_id, media_group_id)
        flush_now = False
        async with self._lock:
            entry = self._groups.get(key)
            if entry is None:
                entry = MediaGroupEntry(
                    chat_id=chat_id,
                    media_group_id=media_group_id,
                    on_flush=on_flush,
                )
                self._groups[key] = entry
            entry.images.extend(images)
            entry.messages.append(message)
            # Every arrival restarts the timer so the flush waits for the last
            # photo of the group, not for the first.
            if entry.task is not None:
                entry.task.cancel()
            if len(entry.images) >= self._max_photos:
                flush_now = True
            else:
                entry.task = asyncio.create_task(self._timer(key, entry))
        if flush_now:
            await self._flush(key, expected=entry)
        return True

    async def _timer(self, key: tuple[int, str], entry: MediaGroupEntry) -> None:
        try:
            await asyncio.sleep(self._debounce_seconds)
        except asyncio.CancelledError:
            # A newer photo of the group restarted the timer — this task is stale.
            return
        await self._flush(key, expected=entry)

    async def _flush(
        self,
        key: tuple[int, str],
        *,
        expected: MediaGroupEntry | None = None,
    ) -> None:
        async with self._lock:
            entry = self._groups.get(key)
            if entry is None:
                return
            if expected is not None and entry is not expected:
                # A newer group replaced this one; its own timer handles it.
                return
            self._groups.pop(key, None)
            # Cancel a still-pending debounce timer (e.g. a cap flush while the
            # timer is still sleeping). When this flush IS the timer task, do
            # NOT cancel it — cancelling the current task would interrupt the
            # ``on_flush`` below and silently drop the whole album (no turn is
            # ever created, nothing reaches the pipeline / Langfuse).
            if (
                entry.task is not None
                and entry.task is not asyncio.current_task()
                and not entry.task.done()
            ):
                entry.task.cancel()
        if entry.on_flush is None:
            return
        try:
            await entry.on_flush(entry)
        except Exception:
            logger.exception(
                "media_group_flush_failed chat_id=%s media_group_id=%s",
                entry.chat_id,
                entry.media_group_id,
            )

    def pending(self) -> int:
        """Number of media groups currently buffered (for observability)."""
        return len(self._groups)
