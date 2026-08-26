import logging

from app.bot.stickers.models import StickerCatalog, StickerDef
from app.config.content import StickersContent, get_content

logger = logging.getLogger(__name__)


def build_catalog(content: StickersContent | None = None) -> StickerCatalog:
    content = content or get_content().stickers
    stickers = [StickerDef.from_content(item) for item in content.stickers]
    return StickerCatalog(set_name=content.sticker_set_name, stickers=stickers)


def _match_remote(remote, index, emoji):
    if index is not None:
        if 0 <= index < len(remote):
            return remote[index]
        return None
    if emoji:
        for candidate in remote:
            if candidate.emoji == emoji:
                return candidate
    return None


async def resolve_file_ids(catalog: StickerCatalog, bot) -> None:
    """Fill runtime file ids from the Telegram sticker set (best effort).

    Priority per sticker: explicit ``file_id`` from config > position ``index`` in
    the pack > first sticker with a matching ``emoji``. Any Telegram failure
    disables stickers gracefully — the bot keeps working without them.
    """
    if not catalog.set_name or not catalog.stickers:
        return
    try:
        sticker_set = await bot.get_sticker_set(catalog.set_name)
    except Exception:
        logger.warning(
            "sticker_set_resolve_failed set_name=%s — stickers disabled",
            catalog.set_name,
            exc_info=True,
        )
        return

    remote = sticker_set.stickers
    resolved = 0
    for sticker in catalog.stickers:
        if sticker.file_id:
            resolved += 1
            continue
        match = _match_remote(remote, sticker.index, sticker.emoji)
        if match is not None:
            sticker.resolved_file_id = match.file_id
            resolved += 1
    logger.info(
        "sticker_set_resolved set_name=%s resolved=%s/%s",
        catalog.set_name,
        resolved,
        len(catalog.stickers),
    )
