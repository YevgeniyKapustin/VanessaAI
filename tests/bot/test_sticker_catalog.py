from services.bot.stickers.models import StickerCatalog, StickerDef
from vanessa.config.content import StickerDefContent, StickersContent
from vanessa.config.content import get_content
from services.bot.stickers.catalog import build_catalog


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
    assert len(stickers.stickers) == 10
    # every sticker is resolvable: explicit file_id or index+emoji (runtime fetch)
    for sticker in stickers.stickers:
        assert (
            sticker.file_id or sticker.index is not None or sticker.emoji
        ), sticker.name
    by_name = {item.name: item for item in stickers.stickers}
    # greeting and farewell are separate stickers (both 👋) with their own tags
    assert "wave_hello" in by_name
    assert set(by_name["wave_hello"].tags) == {"greeting"}
    assert "wave_bye" in by_name
    assert set(by_name["wave_bye"].tags) == {"farewell"}
    assert "thinking" in by_name
    assert set(by_name["thinking"].tags) == {"thinking"}
    # the newer pack emotions: bemused 😐, tease 😏, weary 🫤
    assert set(by_name["bemused"].tags) == {"bemused"}
    assert by_name["bemused"].emoji == "😐"
    assert "странное" in by_name["bemused"].description
    assert set(by_name["smirk"].tags) == {"tease"}
    assert by_name["smirk"].emoji == "😏"
    assert "ироничная" in by_name["smirk"].description
    assert set(by_name["weary"].tags) == {"weary"}
    assert by_name["weary"].emoji == "🫤"
    assert "утомляет" in by_name["weary"].description
    # the emotions are advertised to the LLM
    assert {"bemused", "tease", "weary"} <= set(stickers.available_tags)
    # bemused is a sticker-only tag: the image itself carries the message,
    # so the bot sends it as a bare sticker without a text reply
    assert "bemused" in stickers.sticker_only_tags
    assert stickers.is_sticker_only("bemused") is True
    assert stickers.is_sticker_only("tease") is False
    assert stickers.is_sticker_only("weary") is False
    assert stickers.is_sticker_only(None) is False


def test_tag_lines_render_description():
    content = StickersContent(
        sticker_set_name="VanessaBot",
        stickers=[
            StickerDefContent(
                name="bemused",
                tags=["bemused"],
                emoji="😐",
                description="что-то странное сказали, но отвечаешь",
            ),
            StickerDefContent(name="plain", tags=["love"], emoji="❤️"),
        ],
    )
    lines = content.tag_lines()
    assert "- bemused (😐) — что-то странное сказали, но отвечаешь" in lines
    assert "- love (❤️)" in lines


def test_tag_probability_and_aliases_parse():
    stickers = get_content().stickers
    assert stickers.tag_probability.get("love") == 0.8
    assert stickers.tag_probability.get("thinking") == 0.4
    assert stickers.tag_probability.get("weary") == 0.4
    # every tag_probability key and alias target is a real catalog tag
    assert set(stickers.tag_probability) <= set(stickers.available_tags)
    assert stickers.tag_aliases.get("angry") == "irritation"
    assert stickers.tag_aliases.get("laugh") == "delight"
    assert stickers.tag_aliases.get("tired") == "weary"
    assert set(stickers.tag_aliases.values()) <= set(stickers.available_tags)


def test_xml_system_block_renders_tag_entry():
    content = StickersContent(
        sticker_set_name="VanessaBot",
        system_description="Описание стикеров.",
        tag_rules=["Один тег на сообщение.", "Тег в конце ответа."],
        stickers=[
            StickerDefContent(
                name="hype",
                tags=["delight"],
                emoji="🤩",
                description="восторг, радость",
            ),
        ],
    )
    block = content.xml_system_block()
    assert block.startswith("<sticker_system>")
    assert "<description>Описание стикеров.</description>" in block
    assert '<tag name="delight">🤩 (hype) — восторг, радость</tag>' in block
    assert "<rule>Один тег на сообщение.</rule>" in block
    assert "<rule>Тег в конце ответа.</rule>" in block


def test_xml_system_block_is_well_formed_and_synced():
    import xml.etree.ElementTree as ET

    stickers = get_content().stickers
    block = stickers.xml_system_block()
    root = ET.fromstring(block)  # raises on malformed XML
    tags = [tag.get("name") for tag in root.find("available_tags")]
    assert set(tags) == set(stickers.available_tags)
    # each tag is advertised exactly once
    assert len(tags) == len(set(tags)) == len(stickers.available_tags)
    rules = root.find("tag_rules")
    assert rules is not None and len(rules) == len(stickers.tag_rules)


class _RemoteSticker:
    def __init__(self, emoji: str, file_id: str) -> None:
        self.emoji = emoji
        self.file_id = file_id


class _StickerSet:
    def __init__(self, stickers: list) -> None:
        self.stickers = stickers


class _Bot:
    def __init__(self, stickers: list) -> None:
        self._set = _StickerSet(stickers)

    async def get_sticker_set(self, name: str):
        return self._set


def test_match_remote_prefers_emoji_over_stale_index():
    from services.bot.stickers.catalog import _match_remote

    remote = [
        _RemoteSticker("❤️", "f:heart"),
        _RemoteSticker("🤩", "f:hype"),  # index 1
        _RemoteSticker("👋", "f:wave"),
        _RemoteSticker("🫤", "f:weary"),  # index 3
    ]
    # stale config index (1 -> hype) must not bind a 🫤 sticker to the wrong image
    assert _match_remote(remote, 1, "🫤").file_id == "f:weary"
    # exact index+emoji match still works
    assert _match_remote(remote, 0, "❤️").file_id == "f:heart"
    # positional fallback when no emoji is known
    assert _match_remote(remote, 3, None).file_id == "f:weary"


def test_match_remote_disambiguates_duplicate_emoji_by_index():
    from services.bot.stickers.catalog import _match_remote

    remote = [
        _RemoteSticker("❤️", "f:heart"),
        _RemoteSticker("👋", "f:hello"),  # index 1
        _RemoteSticker("👋", "f:bye"),    # index 2
        _RemoteSticker("🫤", "f:weary"),
    ]
    # two remote stickers share 👋: the exact (index, emoji) match picks the right one
    assert _match_remote(remote, 1, "👋").file_id == "f:hello"
    assert _match_remote(remote, 2, "👋").file_id == "f:bye"


def test_resolve_file_ids_refreshes_baked_ids_from_live_pack():
    import asyncio

    from services.bot.stickers.catalog import build_catalog, resolve_file_ids

    content = StickersContent(
        sticker_set_name="VanessaBot",
        stickers=[
            StickerDefContent(
                name="heart", tags=["love"], emoji="❤️", file_id="f:stale", index=0
            ),
            StickerDefContent(name="weary", tags=["weary"], emoji="🫤", index=7),
        ],
    )
    catalog = build_catalog(content)
    bot = _Bot(
        [
            _RemoteSticker("❤️", "f:live_heart"),
            _RemoteSticker("👋", "f:wave"),
            _RemoteSticker("🤩", "f:hype"),
            _RemoteSticker("😮‍💨", "f:burning"),
            _RemoteSticker("🤔", "f:thinking"),
            _RemoteSticker("🥺", "f:plead"),
            _RemoteSticker("😐", "f:bemused"),
            _RemoteSticker("🫤", "f:live_weary"),
        ]
    )
    asyncio.run(resolve_file_ids(catalog, bot))
    by_name = {s.name: s for s in catalog.stickers}
    # stale baked ids are healed from the live pack
    assert by_name["heart"].file_id == "f:live_heart"
    assert by_name["weary"].file_id == "f:live_weary"
