"""Factory that instantiates the configured web-search provider."""

from __future__ import annotations

import logging

from app.config.settings import settings
from app.services.websearch.duckduckgo import DuckDuckGoSearch
from app.services.websearch.protocols import WebSearchService
from app.services.websearch.serper import SerperSearch
from app.services.websearch.tavily import TavilySearch

logger = logging.getLogger(__name__)


def create_web_search() -> WebSearchService | None:
    """Instantiate the configured search provider, or None when disabled.

    Returns None when ``web_search_enabled`` is off so a deployment without a
    search API behaves exactly as before (the Retrieve stage just skips the
    search). When enabled but the API key is missing, the provider is still
    returned — it logs a warning and returns an empty result (fail-open).
    """
    if not settings.web_search_enabled:
        return None
    provider = settings.web_search_provider.strip().lower()
    if provider == "serper":
        return SerperSearch()
    if provider == "duckduckgo":
        return DuckDuckGoSearch()
    if provider != "tavily":
        logger.warning(
            "web_search_unknown_provider provider=%r, falling back to tavily",
            provider,
        )
    return TavilySearch()
