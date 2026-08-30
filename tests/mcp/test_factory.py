from vanessa.mcp.websearch import McpWebSearch
from vanessa.services.websearch.factory import create_web_search
from vanessa.services.websearch.tavily import TavilySearch


def test_factory_uses_mcp_when_url_set(monkeypatch) -> None:
    from vanessa.config.settings import settings

    monkeypatch.setattr(settings, "mcp_websearch_url", "http://mcp-websearch:8101/mcp")
    monkeypatch.setattr(settings, "web_search_enabled", True)
    result = create_web_search()
    assert isinstance(result, McpWebSearch)


def test_factory_mcp_server_skips_mcp_url(monkeypatch) -> None:
    from vanessa.config.settings import settings

    monkeypatch.setattr(settings, "mcp_websearch_url", "http://mcp-websearch:8101/mcp")
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "web_search_provider", "tavily")
    result = create_web_search(allow_mcp=False)
    assert isinstance(result, TavilySearch)


def test_factory_in_process_when_no_mcp_url(monkeypatch) -> None:
    from vanessa.config.settings import settings

    monkeypatch.setattr(settings, "mcp_websearch_url", "")
    monkeypatch.setattr(settings, "web_search_enabled", True)
    monkeypatch.setattr(settings, "web_search_provider", "tavily")
    result = create_web_search()
    assert isinstance(result, TavilySearch)


def test_factory_none_when_disabled(monkeypatch) -> None:
    from vanessa.config.settings import settings

    monkeypatch.setattr(settings, "mcp_websearch_url", "")
    monkeypatch.setattr(settings, "web_search_enabled", False)
    assert create_web_search() is None
