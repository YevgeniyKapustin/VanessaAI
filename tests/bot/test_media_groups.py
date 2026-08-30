"""Unit tests for the media-group (album) aggregation buffer."""

import asyncio
import time
from types import SimpleNamespace

import pytest

from services.bot.media_groups import MediaGroupBuffer
from vanessa.core.messages import ImageAttachment


def _image(file_id: str) -> ImageAttachment:
    return ImageAttachment(
        data_url="data:image/jpeg;base64,AAAA",
        mime_type="image/jpeg",
        telegram_file_id=file_id,
    )


def _message(caption: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(caption=caption, chat=SimpleNamespace(id=-1001))


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_buffers_whole_group_into_one_flush():
    """All photos of a media group are merged into a single flush entry."""
    buffer = MediaGroupBuffer(debounce_seconds=0.02, max_photos=100)
    flushed: list = []

    # The callback awaits — this is what catches the self-cancellation bug: if
    # the flush cancelled the timer task that called it, the awaiting on_flush
    # would be interrupted and the entry would never arrive.
    async def on_flush(entry):
        await asyncio.sleep(0)
        flushed.append(entry)

    await buffer.add(-1001, "album-1", _message("сравни картины"), [_image("f1")], on_flush)
    await buffer.add(-1001, "album-1", _message(), [_image("f2")], on_flush)

    await _wait_for(lambda: len(flushed) == 1)

    assert len(flushed) == 1
    entry = flushed[0]
    assert entry.chat_id == -1001
    assert entry.media_group_id == "album-1"
    assert [img.telegram_file_id for img in entry.images] == ["f1", "f2"]
    assert len(entry.messages) == 2


@pytest.mark.asyncio
async def test_restarts_timer_on_each_photo_no_early_flush():
    """A photo arriving inside the debounce window extends it — no partial flush."""
    buffer = MediaGroupBuffer(debounce_seconds=0.05, max_photos=100)
    flushed: list = []

    async def on_flush(entry):
        await asyncio.sleep(0)
        flushed.append(entry)

    await buffer.add(-1001, "album-1", _message(), [_image("f1")], on_flush)
    await asyncio.sleep(0.02)  # inside the debounce window
    assert not flushed
    await buffer.add(-1001, "album-1", _message(), [_image("f2")], on_flush)

    await _wait_for(lambda: len(flushed) == 1)
    assert len(flushed) == 1
    assert len(flushed[0].images) == 2


@pytest.mark.asyncio
async def test_flushes_immediately_on_cap():
    """Reaching max_photos flushes right away instead of waiting the debounce."""
    buffer = MediaGroupBuffer(debounce_seconds=10.0, max_photos=2)
    flushed: list = []

    async def on_flush(entry):
        await asyncio.sleep(0)
        flushed.append(entry)

    await buffer.add(-1001, "album-1", _message(), [_image("f1")], on_flush)
    assert not flushed  # below cap — still waiting for the debounce
    await buffer.add(-1001, "album-1", _message(), [_image("f2")], on_flush)
    assert len(flushed) == 1
    assert len(flushed[0].images) == 2


@pytest.mark.asyncio
async def test_separate_groups_flush_independently():
    """Different media groups in the same chat do not merge."""
    buffer = MediaGroupBuffer(debounce_seconds=0.02, max_photos=100)
    flushed: list = []

    async def on_flush(entry):
        await asyncio.sleep(0)
        flushed.append(entry)

    await buffer.add(-1001, "album-1", _message(), [_image("f1")], on_flush)
    await buffer.add(-1001, "album-2", _message(), [_image("f2")], on_flush)

    await _wait_for(lambda: len(flushed) == 2)

    assert len(flushed) == 2
    assert {entry.media_group_id for entry in flushed} == {"album-1", "album-2"}


@pytest.mark.asyncio
async def test_flush_error_is_logged_and_group_consumed():
    """A failing flush callback must not leave the group stuck in the buffer."""
    buffer = MediaGroupBuffer(debounce_seconds=0.01, max_photos=100)
    calls = 0

    async def on_flush(entry):
        await asyncio.sleep(0)
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    await buffer.add(-1001, "album-1", _message(), [_image("f1")], on_flush)
    await _wait_for(lambda: calls == 1)
    assert buffer.pending() == 0
