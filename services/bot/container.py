import logging
from dataclasses import dataclass

from vanessa.config import settings
from vanessa.config.content import BotMessagesContent, get_content
from services.bot.services.api_client import HttpChatApiClient
from services.bot.services.chat_access import ChatAccessGuard
from services.bot.services.protocols import ChatApiClientProtocol
from services.bot.stickers import StickerDecider, StickerService, build_catalog

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BotServices:
    chat_client: ChatApiClientProtocol
    notes_client: object
    access_guard: ChatAccessGuard
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
    # Transport selection: HTTP (legacy /api/v1/chat) or the broker (Redis
    # Streams RPC). The handler code is identical either way — both implement
    # ChatApiClientProtocol.
    if settings.transport == "redis":
        from services.bot.services.broker_client import BrokerTurnClient
        from vanessa.broker.redis_streams import RedisStreamBroker
        from vanessa.broker.streams import BrokerStreams

        chat_client: ChatApiClientProtocol = BrokerTurnClient(
            RedisStreamBroker(
                settings.broker_redis_url,
                stream_maxlen=settings.broker_stream_maxlen,
                dlq_enabled=settings.broker_dlq_enabled,
            ),
            streams=BrokerStreams.from_settings(settings),
            timeout=settings.broker_rpc_timeout_seconds,
        )
        logger.info("bot_transport=redis streams=%s", settings.broker_streams_prefix)
    else:
        chat_client = HttpChatApiClient(
            timeout=settings.api_client_read_timeout,
            connect_timeout=settings.api_client_connect_timeout,
        )

    notes_client = (
        chat_client
        if isinstance(chat_client, HttpChatApiClient)
        else HttpChatApiClient(
            timeout=settings.api_client_read_timeout,
            connect_timeout=settings.api_client_connect_timeout,
        )
    )

    return BotServices(
        chat_client=chat_client,
        notes_client=notes_client,
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
