from services.bot.stickers.heuristics import reply_tags
from services.bot.stickers.models import StickerCatalog


def resolve_candidate(
    catalog: StickerCatalog,
    tag: str | None,
    reply_text: str | None,
) -> tuple[str, bool] | None:
    llm = _llm_tag(catalog, tag)
    if llm is not None:
        return llm
    return _heuristic_tag(catalog, reply_text)


def _llm_tag(
    catalog: StickerCatalog, tag: str | None
) -> tuple[str, bool] | None:
    if not tag:
        return None
    normalized = tag.lower()
    if catalog.stickers_for_tag(normalized):
        return normalized, True
    return None


def _heuristic_tag(
    catalog: StickerCatalog, reply_text: str | None
) -> tuple[str, bool] | None:
    for heuristic_tag in reply_tags(reply_text):
        if catalog.stickers_for_tag(heuristic_tag):
            return heuristic_tag, False
    return None
