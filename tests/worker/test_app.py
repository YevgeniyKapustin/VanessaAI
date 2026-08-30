import asyncio

import fakeredis.aioredis

from vanessa.broker.redis_streams import RedisStreamBroker
from vanessa.contracts.messages import TaskKind, TaskMessage
from services.worker.app import WorkerApp


class _Handler:
    def __init__(self) -> None:
        self.tasks: list[TaskMessage] = []

    async def handle(self, task: TaskMessage) -> None:
        self.tasks.append(task)


async def test_worker_app_dispatches_task() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    handler = _Handler()
    app = WorkerApp(
        broker,
        {TaskKind.INDEX_MESSAGE: handler},
        tasks_stream="vanessa:tasks",
        group="worker",
        consumer="w1",
    )
    consume_task = asyncio.create_task(app._consume_tasks())
    await asyncio.sleep(0.05)
    await broker.publish(
        "vanessa:tasks",
        TaskMessage(task=TaskKind.INDEX_MESSAGE, payload={"message_id": 1}),
    )
    await asyncio.sleep(0.1)
    consume_task.cancel()
    await asyncio.gather(consume_task, return_exceptions=True)

    assert len(handler.tasks) == 1
    assert handler.tasks[0].task == TaskKind.INDEX_MESSAGE


async def test_worker_app_skips_unknown_kind() -> None:
    client = fakeredis.aioredis.FakeRedis()
    broker = RedisStreamBroker("redis://localhost:6379/0", client=client)
    handler = _Handler()
    app = WorkerApp(
        broker,
        {},
        tasks_stream="vanessa:tasks",
        group="worker",
        consumer="w1",
    )
    consume_task = asyncio.create_task(app._consume_tasks())
    await asyncio.sleep(0.05)
    await broker.publish(
        "vanessa:tasks",
        TaskMessage(task=TaskKind.INDEX_MESSAGE, payload={"message_id": 1}),
    )
    await asyncio.sleep(0.1)
    consume_task.cancel()
    await asyncio.gather(consume_task, return_exceptions=True)

    assert handler.tasks == []
