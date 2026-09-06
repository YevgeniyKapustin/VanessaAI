import logging
from collections.abc import Awaitable, Callable

import httpx

from services.bot.container import BotServices
from services.bot.messages import IncomingMessage
from services.bot.messages.response import ChatProcessResult

logger = logging.getLogger("services.bot.handlers.messages")


async def _process_incoming(
    services: BotServices,
    incoming: IncomingMessage,
    start_typing: Callable[[], Awaitable[None]],
) -> ChatProcessResult | None:
    try:
        return await services.chat_client.process(
            incoming,
            on_started=start_typing,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "api_request_error chat_id=%s error=%s",
            incoming.telegram_chat_id,
            exc,
        )
        return None


def _should_ignore(result: ChatProcessResult) -> bool:
    if result.action != "reply":
        return True
    return not result.reply and not result.sticker_tag
