from dataclasses import dataclass

from app.config import settings
from app.config.content import BotMessagesContent, get_content
from app.bot.services.api_client import HttpChatApiClient
from app.bot.services.chat_access import ChatAccessGuard
from app.bot.services.protocols import ChatApiClientProtocol
from app.bot.stickers import StickerDecider, StickerService, build_catalog
from app.knowledge.vault import KnowledgeVault


@dataclass(frozen=True, slots=True)
class BotServices:
    chat_client: ChatApiClientProtocol
    access_guard: ChatAccessGuard
    knowledge: KnowledgeVault
    texts: BotMessagesContent
    stickers: StickerService | None = None
    # How often the bot re-sends the "typing..." chat action while the API
    # pipeline runs (Telegram expires typing after ~5s).
    typing_interval_seconds: float = 4.0
    # Delay (seconds) between consecutive reply blocks of a multi-message reply,
    # so the messages appear one by one ("по мере написания").
    message_delay_seconds: float = 0.7
    # Safety cap on how many reply blocks are sent in one turn.
    max_messages: int = 8


def create_bot_services() -> BotServices:
    content = get_content()
    stickers_config = content.stickers
    catalog = build_catalog(stickers_config)
    decider = StickerDecider(
        catalog,
        enabled=stickers_config.enabled,
        probability=stickers_config.probability,
        heuristic_probability=stickers_config.heuristic_probability,
        min_messages_between=stickers_config.min_messages_between,
        tag_probability=stickers_config.tag_probability,
    )
    return BotServices(
        chat_client=HttpChatApiClient(
            timeout=settings.api_client_read_timeout,
            connect_timeout=settings.api_client_connect_timeout,
        ),
        access_guard=ChatAccessGuard(),
        knowledge=KnowledgeVault(),
        texts=content.bot,
        stickers=StickerService(
            catalog,
            decider,
            sticker_only_tags=tuple(stickers_config.sticker_only_tags),
        ),
        typing_interval_seconds=settings.bot_typing_interval_seconds,
        message_delay_seconds=settings.bot_message_delay_seconds,
        max_messages=settings.bot_max_messages,
    )
