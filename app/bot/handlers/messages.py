import logging

import httpx
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import Message as TelegramMessage

from app.bot.container import BotServices
from app.bot.messages import IncomingMessage
from app.bot.stickers.heuristics import is_sticker_request
from app.bot.telegram_format import markdown_to_telegram_html
from app.decision.models import DecisionAction

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 80


def _preview(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return f"{normalized[:_PREVIEW_LEN]}..."


async def _send_reply(telegram_message: TelegramMessage, reply: str) -> None:
    formatted = markdown_to_telegram_html(reply)
    try:
        await telegram_message.reply(formatted, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await telegram_message.reply(reply)


def create_messages_router(services: BotServices) -> Router:
    router = Router()

    async def _reject_if_no_access(
        telegram_message: TelegramMessage,
        incoming: IncomingMessage,
    ) -> bool:
        error = await services.access_guard.ensure_access(incoming)
        if error:
            logger.info(
                "access_denied chat_id=%s sender_id=%s chat_type=%s",
                incoming.telegram_chat_id,
                incoming.sender_telegram_id,
                incoming.chat_type,
            )
            await telegram_message.answer(error)
            return True
        return False

    @router.message(CommandStart())
    async def cmd_start(telegram_message: TelegramMessage) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        if await _reject_if_no_access(telegram_message, incoming):
            return
        logger.info(
            "command_start chat_id=%s sender_id=%s",
            incoming.telegram_chat_id,
            incoming.sender_telegram_id,
        )
        await telegram_message.answer(services.texts.welcome.strip())
        if services.stickers is not None:
            services.stickers.register_reply(incoming.telegram_chat_id)
            await services.stickers.send_if_any(
                telegram_message,
                sticker_tag="greeting",
            )

    @router.message(F.text)
    async def handle_text(telegram_message: TelegramMessage) -> None:
        incoming = IncomingMessage.from_telegram(telegram_message)
        if await _reject_if_no_access(telegram_message, incoming):
            return

        logger.info(
            "message_received chat_id=%s sender_id=%s text=%r",
            incoming.telegram_chat_id,
            incoming.sender_telegram_id,
            _preview(incoming.text),
        )

        try:
            result = await services.chat_client.process(incoming)
        except httpx.HTTPError:
            await telegram_message.reply(services.texts.error_api)
            return

        if result.action != DecisionAction.REPLY or not result.reply:
            logger.info(
                "message_ignored chat_id=%s reason=%s relevance=%.3f",
                incoming.telegram_chat_id,
                result.reason,
                result.relevance_score,
            )
            return

        sticker_only = (
            services.stickers is not None
            and services.stickers.is_sticker_only(result.sticker_tag)
        )
        if sticker_only:
            # The sticker itself is the whole reply — it already carries a caption
            # on the image, so no text accompanies it. Send it forced: the sticker
            # IS the reply, the anti-spam gate must not swallow the only thing we
            # send. If the sticker can't be sent, fall back to the text answer.
            services.stickers.register_reply(incoming.telegram_chat_id)
            sent = await services.stickers.send_if_any(
                telegram_message,
                sticker_tag=result.sticker_tag,
                reply_text=None,
                force=True,
            )
            logger.info(
                "sticker_only chat_id=%s tag=%s sent=%s",
                incoming.telegram_chat_id,
                result.sticker_tag,
                sent,
            )
            if sent is None:
                await _send_reply(telegram_message, result.reply)
            return

        await telegram_message.bot.send_chat_action(
            incoming.telegram_chat_id,
            "typing",
        )
        await _send_reply(telegram_message, result.reply)
        logger.info(
            "reply_sent chat_id=%s reply_len=%s",
            incoming.telegram_chat_id,
            len(result.reply),
        )
        if services.stickers is not None:
            services.stickers.register_reply(incoming.telegram_chat_id)
            # A direct request («кинь стикер») must always be honoured: bypass
            # the anti-spam probability roll and the cooldown.
            await services.stickers.send_if_any(
                telegram_message,
                sticker_tag=result.sticker_tag,
                reply_text=result.reply,
                force=is_sticker_request(incoming.text),
            )

    return router
