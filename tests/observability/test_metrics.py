import time

from app.observability import metrics


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"error {status_code}")
        self.status_code = status_code


def test_event_window_error_rate() -> None:
    window = metrics.EventWindow(window_seconds=60)
    for _ in range(6):
        window.add("error")
    for _ in range(4):
        window.add("success")
    assert window.count() == 10
    assert window.error_rate(lambda value: value == "error") == 0.6


def test_event_window_percentile() -> None:
    window = metrics.EventWindow(window_seconds=60)
    for value in (1, 2, 3, 4, 5):
        window.add(value)
    assert window.percentile(50) == 3.0
    assert window.percentile(80) == 4.0
    assert window.percentile(100) == 5.0
    assert window.percentile(0) == 1.0


def test_event_window_prunes_old_samples() -> None:
    window = metrics.EventWindow(window_seconds=10)
    window.add("old", at=time.time() - 20)
    window.add("fresh", at=time.time())
    assert window.count() == 1
    assert window.snapshot() == ["fresh"]


def test_event_window_clear() -> None:
    window = metrics.EventWindow(window_seconds=60)
    window.add("a")
    window.clear()
    assert window.count() == 0


def test_classify_llm_error_by_status() -> None:
    cases = {
        401: "auth",
        403: "auth",
        402: "insufficient_balance",
        429: "rate_limit",
        500: "server_error",
        503: "server_error",
    }
    for status, expected in cases.items():
        assert metrics.classify_llm_error(_StatusError(status)) == expected


def test_classify_llm_error_network_and_unknown() -> None:
    assert metrics.classify_llm_error(TimeoutError()) == "network"
    assert metrics.classify_llm_error(ValueError("boom")) == "unknown"


def test_render_metrics_contains_metric_families() -> None:
    metrics.record_turn("reply", "intent")
    text = metrics.render_metrics().decode()
    for name in (
        "vanessa_turns_total",
        "vanessa_turn_duration_seconds",
        "vanessa_stage_duration_seconds",
        "vanessa_llm_tokens_total",
        "vanessa_llm_errors_total",
        "vanessa_rag_score",
        "vanessa_telegram_errors_total",
        "vanessa_process_start_time_seconds",
    ):
        assert name in text


def test_record_llm_call_records_tokens() -> None:
    metrics.llm_outcomes.clear()
    started = time.perf_counter()
    metrics.record_llm_call(
        "deepseek",
        "deepseek-chat",
        "generation",
        started=started,
        status="success",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    assert metrics.llm_outcomes.count() == 1
    text = metrics.render_metrics().decode()
    assert 'token_type="prompt"} 10.0' in text
    assert 'token_type="completion"} 5.0' in text


def test_record_llm_error_adds_window_sample() -> None:
    metrics.llm_outcomes.clear()
    started = time.perf_counter()
    metrics.record_llm_call(
        "deepseek",
        "deepseek-chat",
        "planner",
        started=started,
        status="error",
        error_type="rate_limit",
    )
    assert metrics.llm_outcomes.error_rate(lambda s: s == "error") == 1.0


def test_record_rag_search_counts_empty() -> None:
    metrics.rag_outcomes.clear()
    metrics.record_rag_search("semantic", hits=0, top_score=None)
    assert metrics.rag_outcomes.count() == 1
    assert metrics.rag_outcomes.error_rate(lambda value: value[1] == 0) == 1.0


def test_record_telegram_and_error() -> None:
    metrics.telegram_outcomes.clear()
    metrics.record_telegram("send_reply", "success")
    metrics.record_telegram_error("send_reply", "flood")
    assert metrics.telegram_outcomes.count() == 2
    rate = metrics.telegram_outcomes.error_rate(lambda value: value[1] == "error")
    assert rate == 0.5


def test_queue_length_helper() -> None:
    assert metrics.queue_length() >= 0


def test_prompt_budget_metrics_exposed() -> None:
    metrics.record_prompt_budget("knowledge_blocks", 1234)
    metrics.record_prompt_truncation("context_blocks")
    text = metrics.render_metrics().decode()
    assert "vanessa_prompt_budget_chars" in text
    assert "vanessa_prompt_truncations_total" in text
    assert 'section="knowledge_blocks"' in text
    assert 'section="context_blocks"' in text
