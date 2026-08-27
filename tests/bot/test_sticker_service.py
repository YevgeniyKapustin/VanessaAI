from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.bot.stickers.decider import StickerDecider
from app.bot.stickers.models import StickerCatalog, StickerDef
from app.bot.stickers.service import StickerService
from tests.bot.test_bot_message import make_telegram_message


class _Rng:
    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value

    def choices(self, population, weights=None, *, k=1, cum_weights=None):
        return [population[0]]


def _service() -> tuple[StickerService, StickerDecider]:
    catalog = StickerCatalog(
        set_name="test",
        stickers=[
            StickerDef(
                name="eyes_roll",
                tags=("sarcasm",),
                resolved_file_id="f:sarcasm",
            ),
        ],
    )
    decider = StickerDecider(
        catalog,
        rng=_Rng(0.0),
        probability=1.0,
        heuristic_probability=1.0,
        min_messages_between=10,
    )
    return StickerService(catalog, decider), decider


def test_is_sticker_only():
    catalog = StickerCatalog(
        set_name="test",
        stickers=[
            StickerDef(
                name="bemused",
                tags=("bemused",),
                resolved_file_id="f:bemused",
            ),
        ],
    )
    service = StickerService(
        catalog,
        StickerDecider(catalog),
        sticker_only_tags=("bemused", "weary"),
    )
    assert service.is_sticker_only("bemused") is True
    assert service.is_sticker_only("BEMUSED") is True
    assert service.is_sticker_only("delight") is False
    assert service.is_sticker_only(None) is False
    assert service.is_sticker_only("") is False


def test_is_sticker_only_default_empty():
    catalog = StickerCatalog(
        set_name="test",
        stickers=[StickerDef(name="bemused", tags=("bemused",))],
    )
    service = StickerService(catalog, StickerDecider(catalog))
    assert service.is_sticker_only("bemused") is False


@pytest.mark.asyncio
async def test_send_if_any_sends_sticker():
    message = make_telegram_message()
    message.bot.send_sticker = AsyncMock()
    service, decider = _service()

    sent = await service.send_if_any(message, sticker_tag="sarcasm")

    assert sent == "sarcasm"
    message.bot.send_sticker.assert_awaited_once()
    args = message.bot.send_sticker.await_args.args
    kwargs = message.bot.send_sticker.await_args.kwargs
    assert args[0] == -100123
    assert args[1] == "f:sarcasm"
    # Stickers are sent bare — no reply to the original message.
    assert "reply_to_message_id" not in kwargs
    assert decider.messages_since_sticker(-100123) == 0


@pytest.mark.asyncio
async def test_send_if_any_returns_none_when_no_match():
    message = make_telegram_message()
    message.bot.send_sticker = AsyncMock()
    service, _ = _service()

    sent = await service.send_if_any(message, reply_text="обычное сообщение")

    assert sent is None
    message.bot.send_sticker.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_if_any_swallows_telegram_error():
    message = make_telegram_message()
    message.bot.send_sticker = AsyncMock(
        side_effect=TelegramBadRequest(MagicMock(), "sticker not found")
    )
    service, _ = _service()

    sent = await service.send_if_any(message, sticker_tag="sarcasm")

    assert sent is None


@pytest.mark.asyncio
async def test_register_reply_increments_counter():
    message = make_telegram_message()
    service, decider = _service()
    before = decider.messages_since_sticker(-100123)
    service.register_reply(-100123)
    assert decider.messages_since_sticker(-100123) == before + 1


@pytest.mark.asyncio
async def test_send_if_any_force_bypasses_gates():
    message = make_telegram_message()
    message.bot.send_sticker = AsyncMock()
    service, decider = _service()
    # put the chat deep into cooldown
    decider.register_sticker(-100123)
    for _ in range(5):
        decider.register_reply(-100123)
    assert decider.decide(-100123, tag="sarcasm") is None

    sent = await service.send_if_any(message, sticker_tag="sarcasm", force=True)

    assert sent == "sarcasm"
    message.bot.send_sticker.assert_awaited_once()
