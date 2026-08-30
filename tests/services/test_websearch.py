"""Tests for the live web-search skill (clients, factory, RetrieveStage wiring)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

# Imported before ``vanessa.services``: ``app/services/__init__.py`` eagerly pulls
# the orchestrator, whose import chain (core.session -> decision -> core.session)
# only resolves when ``vanessa.decision`` is already fully loaded. test_orchestrator
# does the same, so this is the established order.
import vanessa.decision  # noqa: F401

from vanessa.config.settings import settings
from vanessa.core.messages import WebResult
from vanessa.core.turn import ChatTurnInput
from vanessa.llm.planner.turn_planner import TurnPlan
from vanessa.services.pipeline.context import TurnPipelineContext
from vanessa.services.pipeline.stages import RetrieveStage
from vanessa.services.websearch.duckduckgo import DuckDuckGoSearch
from vanessa.services.websearch.factory import create_web_search
from vanessa.services.websearch.serper import SerperSearch
from vanessa.services.websearch.tavily import TavilySearch


# --- Tavily ------------------------------------------------------------------

def _tavily_client(payload: dict):
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    client.post.return_value = response
    return client


@pytest.mark.asyncio
async def test_tavily_parses_results_and_forwards_payload():
    client = _tavily_client(
        {
            "results": [
                {
                    "title": "Bitcoin price",
                    "url": "https://example.com/btc",
                    "content": "Bitcoin is trading at 100k",
                    "published_date": "2026-08-28",
                },
                # Missing content is dropped (needs a title or snippet).
                {"url": "https://example.com/empty", "title": "", "content": ""},
            ]
        }
    )
    service = TavilySearch(api_key="secret", client=client)
    results = await service.search("bitcoin цена", limit=3)

    assert len(results) == 1
    result = results[0]
    assert result.title == "Bitcoin price"
    assert result.url == "https://example.com/btc"
    assert result.snippet == "Bitcoin is trading at 100k"
    assert result.published_date == "2026-08-28"

    call = client.post.await_args
    assert call.kwargs["json"]["query"] == "bitcoin цена"
    assert call.kwargs["json"]["max_results"] == 3
    assert call.kwargs["json"]["api_key"] == "secret"
    assert call.kwargs["json"]["search_depth"] == "basic"


@pytest.mark.asyncio
async def test_tavily_without_api_key_returns_empty_without_network():
    client = AsyncMock()
    service = TavilySearch(api_key="", client=client)
    assert await service.search("bitcoin") == []
    client.post.assert_not_awaited()


# --- Serper ------------------------------------------------------------------

def _serper_client(payload: dict):
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    client.post.return_value = response
    return client


@pytest.mark.asyncio
async def test_serper_parses_organic_results():
    client = _serper_client(
        {
            "organic": [
                {
                    "title": "Unity 6 release notes",
                    "link": "https://unity.com/releases",
                    "snippet": "What's new in Unity 6",
                }
            ]
        }
    )
    service = SerperSearch(api_key="secret", client=client)
    results = await service.search("unity 6 release", limit=5)

    assert len(results) == 1
    assert results[0].title == "Unity 6 release notes"
    assert results[0].url == "https://unity.com/releases"
    assert results[0].snippet == "What's new in Unity 6"

    call = client.post.await_args
    assert call.kwargs["json"]["q"] == "unity 6 release"
    assert call.kwargs["headers"]["X-API-KEY"] == "secret"


@pytest.mark.asyncio
async def test_serper_without_api_key_returns_empty_without_network():
    client = AsyncMock()
    service = SerperSearch(api_key="", client=client)
    assert await service.search("unity") == []
    client.post.assert_not_awaited()


# --- DuckDuckGo (best-effort) -------------------------------------------------

_DDG_HTML = """
<div class="result">
  <a rel="nofollow" class="result__a" href="https://en.wikipedia.org/wiki/Bitcoin">Bitcoin - Wikipedia</a>
  <a rel="nofollow" class="result__snippet">Bitcoin is a decentralized digital currency.</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://example.com/btc">&amp; Bitcoin news</a>
</div>
"""


@pytest.mark.asyncio
async def test_duckduckgo_parses_html_results():
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.text = _DDG_HTML
    client.post.return_value = response
    service = DuckDuckGoSearch(client=client)
    results = await service.search("bitcoin", limit=5)

    assert len(results) == 2
    assert results[0].title == "Bitcoin - Wikipedia"
    assert results[0].url == "https://en.wikipedia.org/wiki/Bitcoin"
    assert results[0].snippet == "Bitcoin is a decentralized digital currency."
    assert results[1].title == "& Bitcoin news"


@pytest.mark.asyncio
async def test_duckduckgo_fails_open_on_http_error():
    import httpx

    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.ConnectError("blocked")
    client.post.return_value = response
    service = DuckDuckGoSearch(client=client)
    # The client swallows HTTP errors and returns an empty list (best-effort).
    assert await service.search("bitcoin") == []


# --- Factory -----------------------------------------------------------------

def test_factory_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", False)
    assert create_web_search() is None


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("tavily", TavilySearch),
        ("serper", SerperSearch),
        ("duckduckgo", DuckDuckGoSearch),
        ("unknown", TavilySearch),  # unknown provider falls back to tavily
    ],
)
def test_factory_selects_provider(monkeypatch, provider, expected):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "web_search_provider", provider)
    assert isinstance(create_web_search(), expected)


# --- RetrieveStage wiring (fail-open) ------------------------------------------

class FakeWebSearch:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self._results = results
        self._error = error
        self.called_query: str | None = None
        self.called_limit: int | None = None

    async def search(self, query: str, *, limit: int = 5):
        self.called_query = query
        self.called_limit = limit
        if self._error is not None:
            raise self._error
        return list(self._results or [])


def _stage_ctx(web_search, *, web_search_flag: bool = True, web_query: str = "bitcoin"):
    stage = RetrieveStage(
        retriever=None,
        humor_pipeline=None,
        uow=None,
        web_search=web_search,
    )
    turn = ChatTurnInput(
        telegram_chat_id=1,
        message="какая цена биткоина",
        sender_telegram_id=1,
    )
    ctx = TurnPipelineContext(turn=turn)
    ctx.turn_plan = TurnPlan(
        original=turn.message,
        text="bitcoin цена",
        skip_search=False,
        web_search=web_search_flag,
        web_query=web_query,
    )
    return stage, ctx


@pytest.mark.asyncio
async def test_retrieve_stage_runs_web_search_when_flagged(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    service = FakeWebSearch(
        results=[WebResult(title="Bitcoin", url="https://x/btc", snippet="100k")]
    )
    stage, ctx = _stage_ctx(service)

    await stage._run_web_search(ctx)

    assert service.called_query == "bitcoin"
    assert service.called_limit == settings.web_search_max_results
    assert len(ctx.web_blocks) == 1
    assert ctx.web_blocks[0].title == "Bitcoin"
    assert ctx.web_ms >= 0


@pytest.mark.asyncio
async def test_retrieve_stage_skips_when_not_flagged(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    service = FakeWebSearch(results=[WebResult("t", "u", "s")])
    stage, ctx = _stage_ctx(service, web_search_flag=False)

    await stage._run_web_search(ctx)

    assert service.called_query is None
    assert ctx.web_blocks == []


@pytest.mark.asyncio
async def test_retrieve_stage_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", False)
    service = FakeWebSearch(results=[WebResult("t", "u", "s")])
    stage, ctx = _stage_ctx(service)

    await stage._run_web_search(ctx)

    assert service.called_query is None
    assert ctx.web_blocks == []


@pytest.mark.asyncio
async def test_retrieve_stage_fails_open_on_search_error(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", True)
    service = FakeWebSearch(error=RuntimeError("tavily down"))
    stage, ctx = _stage_ctx(service)

    # Must not raise — the turn proceeds without web results.
    await stage._run_web_search(ctx)

    assert ctx.web_blocks == []


def test_record_web_search_metric_registered():
    from vanessa.observability import metrics as m

    m.record_web_search("found", 12.3)
    m.record_web_search("error", 0.1)

    # The app metrics live on their own CollectorRegistry; Counter collectors
    # expose their name without the trailing ``_total`` suffix.
    names = {collector.name for collector in m.registry.collect()}
    assert "vanessa_web_search" in names
    assert "vanessa_web_search_duration_seconds" in names
