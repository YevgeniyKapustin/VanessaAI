from dataclasses import dataclass

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
    )
    return BotServices(
        chat_client=HttpChatApiClient(),
        access_guard=ChatAccessGuard(),
        knowledge=KnowledgeVault(),
        texts=content.bot,
        stickers=StickerService(
            catalog,
            decider,
            sticker_only_tags=tuple(stickers_config.sticker_only_tags),
        ),
    )
