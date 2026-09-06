import logging
import random

from services.bot.stickers.models import StickerCatalog, StickerPick

logger = logging.getLogger("services.bot.stickers.decider")


def pick_weighted(
    catalog: StickerCatalog, rng: random.Random, tag: str
) -> StickerPick | None:
    candidates = catalog.stickers_for_tag(tag)
    if not candidates:
        return None
    weights = [max(candidate.weight, 0.0) for candidate in candidates]
    if sum(weights) <= 0:
        weights = [1.0] * len(candidates)
    chosen = rng.choices(candidates, weights=weights, k=1)[0]
    assert chosen.available_file_id is not None
    return StickerPick(tag=tag, file_id=chosen.available_file_id)


def pick_random(
    catalog: StickerCatalog,
    rng: random.Random,
    chat_id: int,
    tag: str | None,
) -> StickerPick | None:
    """Force path fallback: user asked for a sticker but no tag resolved."""
    candidates = [
        sticker for sticker in catalog.stickers if sticker.available_file_id
    ]
    if not candidates:
        logger.info(
            "sticker_skip chat_id=%s tag=%r reason=no_available_stickers",
            chat_id,
            tag,
        )
        return None
    chosen = rng.choices(candidates, k=1)[0]
    assert chosen.available_file_id is not None
    chosen_tag = chosen.tags[0] if chosen.tags else "any"
    logger.info(
        "sticker_force_random chat_id=%s requested_tag=%r chosen_tag=%s",
        chat_id,
        tag,
        chosen_tag,
    )
    return StickerPick(tag=chosen_tag, file_id=chosen.available_file_id)
