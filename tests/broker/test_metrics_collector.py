import fakeredis.aioredis

from app.broker.metrics_collector import BrokerMetricsCollector
from app.broker.redis_streams import RedisStreamBroker
from app.broker.streams import BrokerStreams
from app.contracts.messages import TaskKind, TaskMessage


async def test_collector_reports_stream_and_lag() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    streams = BrokerStreams(prefix="vanessa", turns="vanessa:turns", tasks="vanessa:tasks")

    # One task entry, no consumer group → lag should be 0, length 1.
    await broker.publish("vanessa:tasks", TaskMessage(task=TaskKind.SWEEP, payload={}))
    await broker.ensure_group("vanessa:tasks", "worker")

    collector = BrokerMetricsCollector(
        broker,
        streams,
        groups=[("vanessa:turns", "agent-core"), ("vanessa:tasks", "worker")],
    )
    await collector.update_once()

    from app.observability import metrics

    assert metrics.broker_stream_length.labels(stream="vanessa:tasks")._value.get() == 1
    assert metrics.broker_stream_length.labels(stream="vanessa:turns")._value.get() == 0
    assert metrics.broker_dlq_depth.labels(stream="vanessa:tasks")._value.get() == 0
