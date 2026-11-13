import asyncio

from vanessa.contracts.messages import TurnRequest
from vanessa.infrastructure.broker import consume_retry
from vanessa.infrastructure.broker.backends import Delivery, consume_forever
from vanessa.infrastructure.broker.liveness import dead_consumers, unwatch, watch


class _FlakyBackend:
    """First ensure_group call and first read fail, then delivery arrives."""

    def __init__(self, delivery: Delivery, *, read_failures: int = 1) -> None:
        self._delivery = delivery
        self._group_failures = 1
        self._read_failures = read_failures
        self.group_calls = 0
        self.read_calls = 0
        self.acked: list[str] = []
        self.acked_event = asyncio.Event()

    async def ensure_group(self, stream: str, group: str) -> None:
        del stream, group
        self.group_calls += 1
        if self._group_failures:
            self._group_failures -= 1
            raise ConnectionError("redis down")

    async def read(self, *, stream: str, group: str, consumer: str, count: int):
        del stream, group, consumer, count
        self.read_calls += 1
        if self._read_failures:
            self._read_failures -= 1
            raise TimeoutError("redis down")
        if self.read_calls == 2:
            return [self._delivery]
        return []

    async def ack(self, stream: str, group: str, stream_id: str) -> None:
        del stream, group
        self.acked.append(stream_id)
        self.acked_event.set()

    async def reject(self, stream: str, group: str, delivery, error) -> None:
        del stream, group, delivery, error


def _request() -> TurnRequest:
    return TurnRequest(
        correlation_id="c1",
        telegram_chat_id=1,
        message="hello",
        sender_telegram_id=2,
    )


async def test_consume_forever_retries_transport_errors(monkeypatch) -> None:
    monkeypatch.setattr(consume_retry, "_BACKOFF_STEP_SECONDS", 0.0)
    request = _request()
    delivery = Delivery(stream="turns", stream_id="1-0", message=request)
    backend = _FlakyBackend(delivery)
    seen: list[Delivery] = []

    async def handler(handled: Delivery) -> None:
        seen.append(handled)

    task = asyncio.create_task(
        consume_forever(
            backend,
            stream="turns",
            group="agent",
            consumer="c1",
            handler=handler,
            poll_seconds=0.01,
        )
    )
    try:
        await asyncio.wait_for(backend.acked_event.wait(), timeout=2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert backend.group_calls == 2
    assert backend.acked == ["1-0"]
    assert [item.message for item in seen] == [request]


async def test_running_consumer_is_registered_then_released(monkeypatch) -> None:
    monkeypatch.setattr(consume_retry, "_BACKOFF_STEP_SECONDS", 0.0)
    backend = _FlakyBackend(
        Delivery(stream="turns", stream_id="1-0", message=_request()),
        read_failures=0,
    )

    async def handler(handled: Delivery) -> None:
        del handled

    task = asyncio.create_task(
        consume_forever(
            backend,
            stream="live",
            group="agent",
            consumer="c1",
            handler=handler,
            poll_seconds=0.01,
        )
    )
    await asyncio.sleep(0.02)
    assert "consume:agent:live" not in dead_consumers()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert "consume:agent:live" not in dead_consumers()


async def test_dead_consumer_is_reported() -> None:
    async def _finished() -> None:
        return None

    task = asyncio.create_task(_finished())
    watch("consume:test:dead", task)
    try:
        await asyncio.sleep(0)
        assert dead_consumers() == ["consume:test:dead"]
    finally:
        unwatch("consume:test:dead")
    assert "consume:test:dead" not in dead_consumers()
