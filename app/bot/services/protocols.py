from collections.abc import Awaitable, Callable
from typing import Protocol

from app.bot.messages import IncomingMessage
from app.bot.messages.response import ChatProcessResult


class ChatApiClientProtocol(Protocol):
    async def process(
        self,
        message: IncomingMessage,
        on_started: Callable[[], Awaitable[None]] | None = None,
    ) -> ChatProcessResult: ...
