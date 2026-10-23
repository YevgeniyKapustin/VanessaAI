from vanessa.pipeline.turn_metrics import TurnMetrics


def test_turn_metrics_snapshot():
    metrics = TurnMetrics()
    metrics.record_turn(action="reply", reason="intent", deep_search=True)
    metrics.record_turn(action="ignore", reason="prefilter", planner_skipped=True)

    expected_turns = 2
    snap = metrics.snapshot()
    assert snap.total == expected_turns
    assert snap.replies == 1
    assert snap.ignores == 1
    assert snap.deep_search_used == 1
    assert snap.planner_skipped == 1
    assert snap.by_reason["intent"] == 1
