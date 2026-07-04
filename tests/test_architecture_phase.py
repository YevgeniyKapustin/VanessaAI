from app.llm.humor_reflexion import reflexion_filter_humor_quotes
from app.services.turn_metrics import TurnMetrics


def test_reflexion_prefers_theme_matching_quotes():
    quotes = [
        "найди работу личь",
        "просто привет всем",
    ]
    result = reflexion_filter_humor_quotes(
        quotes,
        humor_query="личь работа",
        user_message="ну ладно поработаю",
        max_quotes=1,
    )
    assert result == ["найди работу личь"]


def test_turn_metrics_snapshot():
    metrics = TurnMetrics()
    metrics.record_turn(action="reply", reason="intent", deep_search=True)
    metrics.record_turn(action="ignore", reason="prefilter", planner_skipped=True)

    snap = metrics.snapshot()
    assert snap.total == 2
    assert snap.replies == 1
    assert snap.ignores == 1
    assert snap.deep_search_used == 1
    assert snap.planner_skipped == 1
    assert snap.by_reason["intent"] == 1
