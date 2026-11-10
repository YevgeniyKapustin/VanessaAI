from datetime import UTC, datetime, timedelta

import pytest

from services.worker.announce.compose import Composed
from services.worker.announce.content import WatchSpec
from services.worker.announce.models import Actor, Announcement, Item
from services.worker.announce.watcher import Announcer
from tests.worker.hermes_fakes import FakeBroker
from vanessa.contracts.outbound import OutboundMessage

CHAT = -1000000000001
STREAM = "vanessa:outbound"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
SPEC = WatchSpec(
    id="deploy",
    kind="deploy",
    state_key="vanessa:deploy_last_job",
    path="/deploy/latest",
    header="На прод выкатили в {when}",
    task="TASK",
)


def event(key: int = 2, *, when: datetime | None = None, items: int = 3) -> Announcement:
    return Announcement(
        key=key,
        when=when or NOW - timedelta(minutes=5),
        url="https://git.example/app/-/pipelines/70",
        actor=Actor(name="Viacheslav Titov", username="v.titov"),
        items=tuple(Item(title=f"feat {index}") for index in range(items)),
        total=items,
    )


def parse(payload: dict) -> Announcement | None:
    return payload.get("event")


class FakeSource:
    def __init__(self, announcement: Announcement | None) -> None:
        self.announcement = announcement

    async def payload(self) -> dict:
        return {"event": self.announcement}


class FakeState:
    def __init__(self, key: int | None = None) -> None:
        self.key = key
        self.saved: list[int] = []

    async def last(self) -> int | None:
        return self.key

    async def remember(self, event_id: int) -> None:
        self.key = event_id
        self.saved.append(event_id)


class FakeComposer:
    def __init__(self, text: str = "Выкатили на прод") -> None:
        self.text = text
        self.stand: list[bool | None] = []
        self.mentions: list[object] = []

    async def compose(self, _announcement, *, stand_ready, mention=None) -> str:
        self.stand.append(stand_ready)
        self.mentions.append(mention)
        return self.text

    async def compose_all(self, announcement, *, stand_ready, mention=None):
        text = await self.compose(announcement, stand_ready=stand_ready, mention=mention)
        return Composed(text=text)


def _watcher(
    announcement: Announcement | None,
    *,
    state: FakeState | None = None,
    broker: FakeBroker | None = None,
    composer: FakeComposer | None = None,
    probe_url: str = "",
    probe=None,
):
    kwargs = {}
    if probe is not None:
        kwargs = {"probe": probe, "ready_timeout": timedelta(seconds=0.05)}
    return Announcer(
        SPEC,
        FakeSource(announcement),
        parse,
        composer or FakeComposer(),
        broker or FakeBroker(),
        state or FakeState(),
        outbound_stream=STREAM,
        chat_id=CHAT,
        poll_seconds=0.0,
        probe_url=probe_url,
        **kwargs,
    )


async def test_first_tick_remembers_the_current_event_as_baseline() -> None:
    state, broker = FakeState(), FakeBroker()
    assert await _watcher(event(), state=state, broker=broker).tick(NOW) == 0
    assert state.saved == [2]
    assert broker.published == []


async def test_new_event_is_announced_once() -> None:
    state, broker = FakeState(1), FakeBroker()
    assert await _watcher(event(), state=state, broker=broker).tick(NOW) == 1
    ((stream, message),) = broker.published
    assert stream == STREAM
    assert isinstance(message, OutboundMessage)
    assert message.message_id == "deploy-2"
    assert message.telegram_chat_id == CHAT
    assert message.source == "deploy"
    assert state.saved == [2]
    assert await _watcher(event(), state=state, broker=broker).tick(NOW) == 0


async def test_older_or_same_event_is_ignored() -> None:
    broker = FakeBroker()
    watcher = _watcher(event(2), state=FakeState(5), broker=broker)
    assert await watcher.tick(NOW) == 0
    assert broker.published == []


async def test_empty_source_payload_is_not_an_error() -> None:
    assert await _watcher(None, state=FakeState(1)).tick(NOW) == 0


async def test_stale_event_is_remembered_but_not_posted() -> None:
    state, broker = FakeState(1), FakeBroker()
    old = NOW - timedelta(hours=30)
    assert await _watcher(event(when=old), state=state, broker=broker).tick(NOW) == 0
    assert broker.published == []
    assert state.saved == [2]


async def test_failed_publish_keeps_the_event_for_the_next_tick() -> None:
    state = FakeState(1)
    broker = FakeBroker(error=RuntimeError("redis down"))
    assert await _watcher(event(), state=state, broker=broker).tick(NOW) == 0
    assert state.saved == []
    assert state.key == 1


async def test_stand_probe_result_reaches_the_composer() -> None:
    composer = FakeComposer()

    async def down(url: str) -> bool:
        return False

    watcher = _watcher(
        event(), state=FakeState(1), composer=composer, probe_url="https://prod.example", probe=down
    )
    assert await watcher.tick(NOW) == 1
    assert composer.stand == [False]


async def test_actor_is_resolved_to_a_participant_for_the_mention() -> None:
    composer = FakeComposer()
    asked: list[str] = []

    async def finder(name: str) -> str:
        asked.append(name)
        return "mention"

    watcher = _watcher(event(), state=FakeState(1), composer=composer)
    watcher._mention_finder = finder
    assert await watcher.tick(NOW) == 1
    assert asked == ["Viacheslav Titov"]
    assert composer.mentions == ["mention"]


class _Stop(BaseException):
    """Ends the endless loop in the test (not caught by ``except Exception``)."""


async def test_run_forever_survives_tick_error(monkeypatch) -> None:
    watcher = _watcher(event(), state=FakeState(1))
    calls = 0

    async def tick(now=None) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("bridge down")
        raise _Stop

    monkeypatch.setattr(watcher, "tick", tick)
    with pytest.raises(_Stop):
        await watcher.run_forever()
    assert calls == 2
