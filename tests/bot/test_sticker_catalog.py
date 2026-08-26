from app.bot.stickers.models import StickerCatalog, StickerDef
from app.config.content import StickerDefContent, StickersContent
from app.config.content import get_content
from app.bot.stickers.catalog import build_catalog


def _catalog() -> StickerCatalog:
    return StickerCatalog(
        set_name="test",
        stickers=[
            StickerDef(
                name="eyes_roll",
                tags=("sarcasm", "disapproval"),
                resolved_file_id="f:eyes",
            ),
            StickerDef(
                name="hype",
                tags=("delight",),
                resolved_file_id="f:hype",
            ),
            StickerDef(name="unresolved", tags=("work",)),
        ],
    )


def test_catalog_indexes_by_tag():
    catalog = _catalog()
    sarcasm = catalog.stickers_for_tag("sarcasm")
    assert [s.name for s in sarcasm] == ["eyes_roll"]
    # only stickers with an actual file id are returned
    assert catalog.stickers_for_tag("work") == []


def test_catalog_is_case_insensitive():
    catalog = _catalog()
    assert catalog.stickers_for_tag("DELIGHT")[0].name == "hype"


def test_has_resolved_files():
    assert _catalog().has_resolved_files is True
    empty = StickerCatalog(
        set_name="test",
        stickers=[StickerDef(name="a", tags=("x",))],
    )
    assert empty.has_resolved_files is False


def test_explicit_file_id_wins_over_resolved():
    sticker = StickerDef(
        name="a",
        tags=("x",),
        file_id="f:explicit",
        resolved_file_id="f:resolved",
    )
    assert sticker.available_file_id == "f:explicit"


def test_from_content_skips_empty_file_id():
    item = StickerDefContent(
        name="x",
        tags=["Sarcasm"],
        file_id="",
        index=None,
    )
    sticker = StickerDef.from_content(item)
    assert sticker.tags == ("sarcasm",)
    assert sticker.file_id is None


def test_build_catalog_from_content():
    content = StickersContent(
        sticker_set_name="VanessaBot",
        stickers=[
            StickerDefContent(name="eyes_roll", tags=["sarcasm"], file_id="f:1"),
        ],
    )
    catalog = build_catalog(content)
    assert catalog.set_name == "VanessaBot"
    assert catalog.stickers_for_tag("sarcasm")[0].name == "eyes_roll"


def test_real_config_parses_and_has_live_stickers():
    stickers = get_content().stickers
    assert stickers.enabled is True
    assert stickers.sticker_set_name == "VanessaBot"
    # synced from the live pack (https://t.me/addstickers/VanessaBot)
    assert len(stickers.stickers) == 6
    # every sticker is ready to send: explicit file_id present
    for sticker in stickers.stickers:
        assert sticker.file_id, sticker.name
    by_name = {item.name: item for item in stickers.stickers}
    assert "wave" in by_name
    assert set(by_name["wave"].tags) == {"greeting", "farewell"}
    assert "thinking" in by_name
    assert set(by_name["thinking"].tags) == {"thinking"}
