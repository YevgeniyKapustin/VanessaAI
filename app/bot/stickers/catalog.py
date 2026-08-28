import logging

from app.bot.stickers.models import StickerCatalog, StickerDef
from app.config.content import StickersContent, get_content

logger = logging.getLogger(__name__)


def build_catalog(content: StickersContent | None = None) -> StickerCatalog:
    content = content or get_content().stickers
    stickers = [StickerDef.from_content(item) for item in content.stickers]
    return StickerCatalog(set_name=content.sticker_set_name, stickers=stickers)


def _match_remote(remote, index, emoji):
    """Find the live sticker for a config entry.

    Resolution order:
    1. exact (``index``, ``emoji``) match — disambiguates stickers that share an
       emoji (e.g. two 👋 for wave_hello / wave_bye);
    2. a *unique* emoji match — the reliable semantic signal, so a stale index
       never binds a config sticker to the wrong remote image;
    3. positional ``index`` fallback.
    """
    if index is not None and 0 <= index < len(remote) and remote[index].emoji == emoji:
        return remote[index]
    if emoji:
        candidates = [candidate for candidate in remote if candidate.emoji == emoji]
        if len(candidates) == 1:
            return candidates[0]
    if index is not None and 0 <= index < len(remote):
        return remote[index]
    return None


async def resolve_file_ids(catalog: StickerCatalog, bot) -> None:
    """Fill runtime file ids from the Telegram sticker set (best effort).

    The live pack is the source of truth at startup: every config sticker is
    matched to a remote one (by index+emoji, emoji, or index) and its file id is
    refreshed, so baked ids in the config heal automatically when the pack's
    links change. If the Telegram fetch fails, the config's ``file_id`` values are
    kept and stickers still work offline.
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
        match = _match_remote(remote, sticker.index, sticker.emoji)
        if match is not None:
            sticker.file_id = match.file_id
            sticker.resolved_file_id = None
            resolved += 1
    logger.info(
        "sticker_set_resolved set_name=%s resolved=%s/%s",
        catalog.set_name,
        resolved,
        len(catalog.stickers),
    )
