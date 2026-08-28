"""Value objects for live web search results.

``WebResult`` lives in ``app.core.messages`` (alongside the other shared message
types) so the LLM provider protocol can reference it without importing this
service package — importing ``app.services`` from ``app.core`` would create an
import cycle. This module re-exports it for web-search-internal callers.
"""

from app.core.messages import WebResult

__all__ = ["WebResult"]
