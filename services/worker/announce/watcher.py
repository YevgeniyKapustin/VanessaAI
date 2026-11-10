"""Turn new events from any source into one chat message per event.

One tick: ask the source for its newest event, compare the id with the last
announced one, wait (briefly) for the stand to answer, then compose and
publish. The id is remembered only after the publish, so a failed publish
retries on the next tick; an event older than ``max_late`` (the worker was
down) is remembered, never posted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from services.worker.announce.content import WatchSpec
from services.worker.announce.models import Announcement
from services.worker.announce.prompt import now_utc
from services.worker.announce.source import stand_answers
from vanessa.contracts.outbound import OutboundMessage

logger = logging.getLogger(__name__)

Parser = Callable[[dict], Announcement | None]


def outbound_message(
    spec: WatchSpec,
    announcement: Announcement,
    text: str,
    chat_id: int,
    *,
    rich_html: str | None = None,
) -> OutboundMessage:
    """The message id is stable per event, so a retry cannot double-post."""
    return OutboundMessage(
        message_id=f"{spec.id}-{announcement.key}",
        channel="telegram",
        telegram_chat_id=chat_id,
        text=text,
        source=spec.id,
        rich_html=rich_html,
    )


class Announcer:
    """Polling loop for one watch."""

    def __init__(
        self,
        spec: WatchSpec,
        source,
        parse: Parser,
        composer,
        broker,
        state,
        *,
        outbound_stream: str,
        chat_id: int,
        poll_seconds: float | None = None,
        max_late: timedelta | None = None,
        ready_timeout: timedelta | None = None,
        ready_poll: float | None = None,
        probe_url: str = "",
        probe=stand_answers,
        mention_finder=None,
    ) -> None:
        self._spec = spec
        self._source = source
        self._parse = parse
        self._composer = composer
        self._broker = broker
        self._state = state
        self._stream = outbound_stream
        self._chat_id = chat_id
        self._poll_seconds = spec.poll_seconds if poll_seconds is None else poll_seconds
        self._max_late = max_late or timedelta(hours=spec.max_late_hours)
        self._ready_timeout = (
            ready_timeout or timedelta(seconds=spec.ready_timeout_seconds)
        )
        self._ready_poll = spec.ready_poll_seconds if ready_poll is None else ready_poll
        self._probe_url = probe_url
        self._probe = probe
        self._mention_finder = mention_finder

    @property
    def spec(self) -> WatchSpec:
        return self._spec

    async def run_forever(self) -> None:
        logger.info(
            "announce_started watch=%s poll_seconds=%s chat_id=%s",
            self._spec.id,
            self._poll_seconds,
            self._chat_id,
        )
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("announce_tick_failed watch=%s", self._spec.id)
            await asyncio.sleep(self._poll_seconds)

    async def tick(self, now: datetime | None = None) -> int:
        """Announce one new event; return how many messages were published."""
        announcement = self._parse(await self._source.payload())
        if announcement is None:
            return 0
        if await self._decide(announcement, now or now_utc()) != "announce":
            return 0
        return await self._announce(announcement)

    async def _decide(self, announcement: Announcement, now: datetime) -> str:
        """``baseline`` / ``seen`` / ``stale`` decide without posting."""
        last = await self._state.last()
        if last is None:
            # First run (or a flushed marker): this event is the baseline.
            await self._state.remember(announcement.key)
            logger.info(
                "announce_baseline watch=%s key=%s", self._spec.id, announcement.key
            )
            return "baseline"
        if announcement.key <= last:
            return "seen"
        if self._is_stale(announcement, now):
            await self._state.remember(announcement.key)
            logger.warning(
                "announce_stale watch=%s key=%s", self._spec.id, announcement.key
            )
            return "stale"
        return "announce"

    def _is_stale(self, announcement: Announcement, now: datetime) -> bool:
        if announcement.when is None:
            return False
        return now - _aware(announcement.when) > self._max_late

    async def _announce(self, announcement: Announcement) -> int:
        ready = await self._wait_ready()
        mention = await self._mention(announcement)
        composed = await self._composer.compose_all(
            announcement, stand_ready=ready, mention=mention
        )
        text = composed.text
        message = outbound_message(
            self._spec, announcement, text, self._chat_id, rich_html=composed.rich_html
        )
        try:
            await self._broker.publish(self._stream, message)
        except Exception:
            logger.exception(
                "announce_publish_failed watch=%s key=%s",
                self._spec.id,
                announcement.key,
            )
            return 0
        await self._state.remember(announcement.key)
        logger.info(
            "announce_published watch=%s key=%s chat_id=%s items=%s stand_ready=%s len=%s",
            self._spec.id,
            announcement.key,
            self._chat_id,
            announcement.item_total,
            ready,
            len(text),
        )
        return 1

    async def _wait_ready(self) -> bool | None:
        """Probe the public stand: None when no probe is configured."""
        if not self._probe_enabled():
            return None
        deadline = time.monotonic() + self._ready_timeout.total_seconds()
        while not await self._probe(self._probe_url):
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(self._ready_poll)
        return True

    def _probe_enabled(self) -> bool:
        return bool(self._probe_url) and self._ready_timeout > timedelta(0)

    async def _mention(self, announcement: Announcement):
        """The chat participant behind the actor, if known and enabled."""
        if self._mention_finder is None or not self._spec.mention:
            return None
        actor = announcement.actor
        name = (actor.name if actor else "") or (actor.username if actor else "")
        if not name:
            return None
        return await self._mention_finder(name)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


__all__ = ["Announcer", "Parser", "outbound_message"]
