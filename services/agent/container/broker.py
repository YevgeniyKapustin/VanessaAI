from __future__ import annotations

from vanessa.config.settings import settings


class BrokerResources:
    def __init__(
        self,
        client=None,
        dispatcher=None,
        *,
        dispatch_tasks: bool | None = None,
    ) -> None:
        self._client = client
        self._dispatcher = dispatcher
        if dispatch_tasks is None:
            from services.agent.container.role import ProcessRole

            dispatch_tasks = ProcessRole.from_settings().dispatches_tasks
        self._dispatch_tasks = dispatch_tasks

    def ensure_client(self):
        if self._client is None:
            from vanessa.infrastructure.broker.redis_streams import (
                RedisStreamBroker,
            )

            self._client = RedisStreamBroker(
                settings.broker_redis_url,
                stream_maxlen=settings.broker_stream_maxlen,
                dlq_enabled=settings.broker_dlq_enabled,
            )
        return self._client

    def task_dispatcher(self):
        if not self._dispatch_tasks:
            return None
        if self._dispatcher is None:
            from vanessa.infrastructure.broker.dispatcher import (
                BrokerTaskDispatcher,
            )
            from vanessa.infrastructure.broker.streams import BrokerStreams

            streams = BrokerStreams.from_settings(settings)
            self._dispatcher = BrokerTaskDispatcher(
                self.ensure_client(),
                tasks_stream=streams.tasks,
            )
        return self._dispatcher

    async def close(self) -> None:
        if self._client is None:
            return
        await self._client.close()
        self._client = None
        self._dispatcher = None
