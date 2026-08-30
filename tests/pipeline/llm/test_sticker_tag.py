from vanessa.config.content import get_content
from vanessa.pipeline.llm.format.sticker_tag import (
    KNOWN_STICKER_TAGS,
    TAG_ALIASES,
    extract_sticker_tag,
)


def test_strips_marker_at_the_end():
    cleaned, tag = extract_sticker_tag("Ну да, попал в десятку\n[sticker:delight]")
    assert tag == "delight"
    assert cleaned == "Ну да, попал в десятку"


def test_no_marker_passthrough():
    cleaned, tag = extract_sticker_tag("просто текст без маркера")
    assert tag is None
    assert cleaned == "просто текст без маркера"


def test_empty_input():
    assert extract_sticker_tag("") == ("", None)


def test_unknown_tag_stripped_but_dropped():
    cleaned, tag = extract_sticker_tag("текст [sticker:not_a_tag]")
    assert tag is None
    assert "sticker" not in cleaned


def test_case_insensitive_marker():
    cleaned, tag = extract_sticker_tag("[STICKER:DELIGHT]")
    assert tag == "delight"
    assert cleaned == ""


def test_marker_inside_code_block_is_kept():
    reply = "```python\n[sticker:sarcasm]\n```"
    cleaned, tag = extract_sticker_tag(reply)
    assert tag is None
    assert cleaned == reply


def test_multiple_markers_first_known_wins():
    cleaned, tag = extract_sticker_tag("a [sticker:delight] b [sticker:sarcasm]")
    assert tag == "delight"
    assert "sticker" not in cleaned


def test_marker_after_code_block():
    reply = "```\ncode\n```\n\n[sticker:thinking]"
    cleaned, tag = extract_sticker_tag(reply)
    assert tag == "thinking"
    assert "sticker" not in cleaned
    assert "```\ncode\n```" in cleaned


def test_known_tags_match_catalog_single_source_of_truth():
    """Allowed tags must equal the tags that actually have a sticker in the pack."""
    catalog_tags = frozenset(get_content().stickers.available_tags)
    assert KNOWN_STICKER_TAGS == catalog_tags


def test_tag_without_catalog_sticker_is_dropped():
    """A tag the pack doesn't have (and has no alias) must be stripped, never leaked."""
    missing = "facepalm"
    if missing in KNOWN_STICKER_TAGS or missing in TAG_ALIASES:
        return  # became a real/aliased tag — nothing to check
    cleaned, tag = extract_sticker_tag(f"текст [sticker:{missing}]")
    assert tag is None
    assert "sticker" not in cleaned


def test_unknown_tag_mapped_to_alias():
    """An invented tag with an alias resolves to the closest real tag."""
    cleaned, tag = extract_sticker_tag("текст [sticker:angry]")
    assert tag == "irritation"
    assert "sticker" not in cleaned


def test_alias_is_case_insensitive():
    cleaned, tag = extract_sticker_tag("[STICKER:Angry]")
    assert tag == "irritation"
    assert cleaned == ""


def test_alias_first_known_wins():
    cleaned, tag = extract_sticker_tag("a [sticker:laugh] b [sticker:angry]")
    assert tag == "delight"
    assert "sticker" not in cleaned


def test_real_tag_preferred_over_alias():
    cleaned, tag = extract_sticker_tag("a [sticker:laugh] b [sticker:delight]")
    assert tag == "delight"
    assert "sticker" not in cleaned


def test_unknown_tag_without_alias_dropped():
    """A tag that isn't in the pack and has no alias is dropped, not leaked."""
    missing = "gloomy"
    if missing in KNOWN_STICKER_TAGS or missing in TAG_ALIASES:
        return  # became real/aliased — nothing to check
    cleaned, tag = extract_sticker_tag(f"текст [sticker:{missing}]")
    assert tag is None
    assert "sticker" not in cleaned
