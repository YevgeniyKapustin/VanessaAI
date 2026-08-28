"""Live web search for the compose prompt ("the googling skill").

Search-then-inject: the gate planner flags a turn (``TurnPlan.web_search``),
the Retrieve stage runs one search API call, and the results are injected into
the composer prompt as a bounded "live web results" block. No tool-calling loop,
so no extra LLM round-trip on the answer path.
"""

from app.services.websearch.models import WebResult
from app.services.websearch.protocols import WebSearchService
from app.services.websearch.factory import create_web_search

__all__ = [
    "WebResult",
    "WebSearchService",
    "create_web_search",
]
