import logging
from dataclasses import dataclass

from services.bot.services.broker_client import BrokerTurnClient
from services.bot.services.chat_access import ChatAccessGuard
from services.bot.services.protocols import ChatApiClientProtocol
from services.bot.stickers import StickerDecider, StickerService, build_catalog
from vanessa.config import settings
from vanessa.config.content import BotMessagesContent, get_content
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BotServices:
    chat_client: ChatApiClientProtocol
    notes_client: object
    access_guard: ChatAccessGuard
    texts: BotMessagesContent
    stickers: StickerService | None = None
    typing_interval_seconds: float = 4.0
    message_delay_seconds: float = 0.7
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
    broker = RedisStreamBroker(
        settings.broker_redis_url,
        stream_maxlen=settings.broker_stream_maxlen,
        dlq_enabled=settings.broker_dlq_enabled,
    )
    streams = BrokerStreams.from_settings(settings)
    chat_client = BrokerTurnClient(
        broker,
        streams=streams,
        timeout=settings.broker_rpc_timeout_seconds,
    )
    logger.info("bot_transport=redis streams=%s", settings.broker_streams_prefix)

    return BotServices(
        chat_client=chat_client,
        notes_client=chat_client,
        access_guard=ChatAccessGuard(),
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
