from app.config import settings
from app.rag.hybrid_search import effective_window_max_total


def test_effective_window_max_total_scales_with_anchors():
    per_window = (
        settings.rag_context_window_before
        + 1
        + settings.rag_context_window_after
    )
    assert effective_window_max_total(10) == max(
        settings.rag_context_window_max_total,
        10 * per_window,
    )
