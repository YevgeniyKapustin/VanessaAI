"""Tests for the live web-results block in the compose prompt."""

from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.core.messages import WebResult
from vanessa.llm.prompts.prompt_builder import PromptBuilder


def _builder() -> PromptBuilder:
    return PromptBuilder()


def test_web_block_rendered_with_title_url_snippet_and_date():
    prompt = _builder().build_user_prompt(
        "какая цена биткоина",
        [],
        web_blocks=[
            WebResult(
                title="Bitcoin price",
                url="https://example.com/btc",
                snippet="Bitcoin is trading at 100k",
                published_date="2026-08-28",
            )
        ],
    )

    llm = get_content().llm
    assert llm.web_header.strip() in prompt
    # Line format: "[{date}] - {title} ({url}):\n  {snippet}"
    assert "[2026-08-28]" in prompt
    assert "Bitcoin price (https://example.com/btc):" in prompt
    assert "Bitcoin is trading at 100k" in prompt
    # The honesty / freshness directive rides along with the block.
    assert "LIVE search results" in prompt


def test_no_web_header_without_web_blocks():
    prompt = _builder().build_user_prompt("привет", [])
    assert get_content().llm.web_header.strip() not in prompt
    assert "LIVE search results" not in prompt


def test_web_snippet_truncated_by_settings_cap(monkeypatch):
    monkeypatch.setattr(settings, "web_search_snippet_max_chars", 20)
    long_snippet = "x" * 200
    prompt = _builder().build_user_prompt(
        "вопрос",
        [],
        web_blocks=[WebResult(title="Title", url="https://u", snippet=long_snippet)],
    )
    assert long_snippet not in prompt
    # The header survived the snippet cap (the block itself is still rendered).
    assert get_content().llm.web_header.strip() in prompt


def test_web_block_yields_to_prompt_budget(monkeypatch):
    # A tight per-section cap truncates the whole web block, so a long snippet
    # must not leak into the prompt.
    budget = get_content().llm.budget
    monkeypatch.setattr(budget, "web_blocks", 25)
    long_snippet = "x" * 200
    prompt = _builder().build_user_prompt(
        "вопрос",
        [],
        web_blocks=[WebResult(title="Title", url="https://u", snippet=long_snippet)],
    )
    assert long_snippet not in prompt


def test_web_priority_below_archive_in_budget(monkeypatch):
    """Web results have LOWER budget priority than the archive: under a tight
    global cap, the archive survives and the web block is dropped first."""
    from vanessa.llm.prompts.budget import PRIORITY_KNOWLEDGE, PRIORITY_WEB, apply_budget

    budget = get_content().llm.budget
    monkeypatch.setattr(budget, "max_chars", 400)
    monkeypatch.setattr(budget, "knowledge_blocks", 0)
    monkeypatch.setattr(budget, "web_blocks", 0)

    parts = [
        (PRIORITY_KNOWLEDGE, "knowledge_blocks", "A" * 400),
        (PRIORITY_WEB, "web_blocks", "B" * 200),
    ]
    result = apply_budget(parts, budget, enabled=True)

    bodies = [body for _, _, body in result]
    assert "A" * 400 in bodies  # archive survives fully
    assert not any("B" in body for _, _, body in result)  # web dropped
