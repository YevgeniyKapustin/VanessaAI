"""The composer's [reaction:<emoji>] marker: parse, validate, strip."""

import pytest

from vanessa.pipeline.llm.format.reaction_tag import (
    extract_reaction,
    is_allowed_reaction,
)


def test_extracts_a_trailing_reaction_marker():
    clean, emoji = extract_reaction("ну и денёк\n[reaction:🔥]")

    assert clean == "ну и денёк"
    assert emoji == "🔥"


def test_reaction_only_reply_leaves_no_text():
    clean, emoji = extract_reaction("[reaction:👍]")

    assert clean == ""
    assert emoji == "👍"


def test_keeps_only_the_first_reaction():
    clean, emoji = extract_reaction("ага [reaction:💩] [reaction:🔥]")

    assert emoji == "💩"
    assert "[reaction" not in clean


def test_unknown_emoji_is_dropped_but_the_text_survives():
    clean, emoji = extract_reaction("текст [reaction:🦄]")

    assert clean.strip() == "текст"
    assert emoji is None


def test_russian_marker_spelling_is_accepted():
    clean, emoji = extract_reaction("ладно\n[реакция:❤]")

    assert clean == "ладно"
    assert emoji == "❤"


def test_marker_inside_a_code_fence_is_left_alone():
    reply = "код:\n```\n[reaction:🔥]\n```"

    clean, emoji = extract_reaction(reply)

    assert clean == reply
    assert emoji is None


def test_plain_reply_has_no_reaction():
    assert extract_reaction("просто текст") == ("просто текст", None)


@pytest.mark.parametrize("emoji", ["🔥", "❤", "👍", "🎉"])
def test_telegram_reactions_are_allowed(emoji: str):
    assert is_allowed_reaction(emoji) is True


def test_heart_with_variation_selector_is_allowed():
    assert is_allowed_reaction("❤\ufe0f") is True


def test_arbitrary_emoji_is_rejected():
    assert is_allowed_reaction("🦄") is False
    assert is_allowed_reaction("") is False
