from dataclasses import dataclass

from app.config.content import BotMessagesContent, get_content
from app.bot.services.api_client import HttpChatApiClient
from app.bot.services.chat_access import ChatAccessGuard
from app.bot.services.protocols import ChatApiClientProtocol


@dataclass(frozen=True, slots=True)
class BotServices:
    chat_client: ChatApiClientProtocol
    access_guard: ChatAccessGuard
    texts: BotMessagesContent


def create_bot_services() -> BotServices:
    content = get_content()
    return BotServices(
        chat_client=HttpChatApiClient(),
        access_guard=ChatAccessGuard(),
        texts=content.bot,
    )
