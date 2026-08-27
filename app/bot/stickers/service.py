import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message as TelegramMessage

from app.bot.stickers.catalog import resolve_file_ids
from app.bot.stickers.decider import StickerDecider
from app.bot.stickers.models import StickerCatalog

logger = logging.getLogger(__name__)


class StickerService:
    """Glue between the Telegram handler, the catalog and the anti-spam decider."""

    def __init__(
        self,
        catalog: StickerCatalog,
        decider: StickerDecider,
        sticker_only_tags: tuple[str, ...] = (),
    ) -> None:
        self._catalog = catalog
        self._decider = decider
        self._sticker_only_tags = frozenset(
            tag.lower() for tag in sticker_only_tags
        )

    def is_sticker_only(self, tag: str | None) -> bool:
        """True when the tag is sent as a bare sticker, no text reply.

        The sticker image itself carries the message (e.g. bemused 😐 has a
        caption on it), so the handler suppresses the accompanying text.
        """
        return bool(tag) and tag.lower() in self._sticker_only_tags

    async def resolve_file_ids(self, bot) -> None:
        await resolve_file_ids(self._catalog, bot)

    def register_reply(self, chat_id: int) -> None:
        self._decider.register_reply(chat_id)

    async def send_if_any(
        self,
        telegram_message: TelegramMessage,
        sticker_tag: str | None = None,
        reply_text: str | None = None,
        *,
        force: bool = False,
    ) -> str | None:
        """Decide and send at most one sticker for the current reply.

        ``force`` bypasses the anti-spam gates — use it only for explicit user
        requests (e.g. «кинь стикер»). Returns the tag that was actually sent,
        or ``None``. A sticker must never break the text reply, so Telegram errors
        are logged and swallowed.
        """
        pick = self._decider.decide(
            telegram_message.chat.id,
            tag=sticker_tag,
            reply_text=reply_text,
            force=force,
        )
        if pick is None:
            return None
        try:
            # Stickers are sent bare — no reply_to_message_id — so they don't
            # clutter the chat with an extra quote block on top of the image.
            await telegram_message.bot.send_sticker(
                telegram_message.chat.id,
                pick.file_id,
            )
        except TelegramBadRequest:
            logger.warning(
                "sticker_send_failed chat_id=%s tag=%s",
                telegram_message.chat.id,
                pick.tag,
                exc_info=True,
            )
            return None
        except Exception:
            logger.warning(
                "sticker_send_error chat_id=%s tag=%s",
                telegram_message.chat.id,
                pick.tag,
                exc_info=True,
            )
            return None
        self._decider.register_sticker(telegram_message.chat.id)
        logger.info(
            "sticker_sent chat_id=%s tag=%s",
            telegram_message.chat.id,
            pick.tag,
        )
        return pick.tag
