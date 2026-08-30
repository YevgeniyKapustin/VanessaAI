import asyncio

import fakeredis.aioredis

from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.contracts.messages import TaskKind
from vanessa.infrastructure.broker.dispatcher import BrokerTaskDispatcher


async def test_broker_dispatcher_publishes_task() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    dispatcher = BrokerTaskDispatcher(broker, tasks_stream="vanessa:tasks")

    dispatcher.submit(TaskKind.INDEX_MESSAGE, {"message_id": 7}, dedup_key="index:7")
    await asyncio.sleep(0.05)  # fire-and-forget publish completes

    response = await client.xread({"vanessa:tasks": "0"})
    assert response
    _, entries = response[0]
    assert len(entries) == 1
    _, fields = entries[0]
    assert fields[b"kind"] == b"task"
