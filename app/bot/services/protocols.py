from typing import Protocol

from app.bot.messages import IncomingMessage
from app.bot.messages.response import ChatProcessResult


class ChatApiClientProtocol(Protocol):
    async def process(self, message: IncomingMessage) -> ChatProcessResult: ...
