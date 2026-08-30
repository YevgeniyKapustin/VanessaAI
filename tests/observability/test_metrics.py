import time

import pytest

from vanessa.config.settings import settings
from vanessa.observability import metrics


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


def test_start_metrics_http_server_serves_health(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_require_token", False)
    server = metrics.start_metrics_http_server(0, addr="127.0.0.1")
    try:
        host, port = server.server_address
        from urllib.request import urlopen

        with urlopen(f"http://{host}:{port}/health", timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"ok\n"
        with urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:
            assert response.status == 200
            body = response.read()
            assert b"vanessa_" in body or b"#" in body
    finally:
        server.shutdown()
        server.server_close()


def test_start_metrics_http_server_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_require_token", True)
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    server = metrics.start_metrics_http_server(0, addr="127.0.0.1")
    try:
        host, port = server.server_address
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        with urlopen(f"http://{host}:{port}/health", timeout=2) as response:
            assert response.status == 200
        try:
            urlopen(f"http://{host}:{port}/metrics", timeout=2)
            raise AssertionError("expected 401")
        except HTTPError as exc:
            assert exc.code == 401
        req = Request(
            f"http://{host}:{port}/metrics",
            headers={"X-Internal-Token": "secret"},
        )
        with urlopen(req, timeout=2) as response:
            assert response.status == 200
        bearer = Request(
            f"http://{host}:{port}/metrics",
            headers={"Authorization": "Bearer secret"},
        )
        with urlopen(bearer, timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_metrics_token_allowed_respects_flag(monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_require_token", False)
    assert metrics.metrics_token_allowed({}) is True
    monkeypatch.setattr(settings, "metrics_require_token", True)
    monkeypatch.setattr(settings, "api_internal_token", "")
    assert metrics.metrics_token_allowed({}) is True
    monkeypatch.setattr(settings, "api_internal_token", "secret")
    assert metrics.metrics_token_allowed({}) is False
    assert metrics.metrics_token_allowed({"X-Internal-Token": "secret"}) is True
    assert metrics.metrics_token_allowed(
        {"Authorization": "Bearer secret"}
    ) is True


def test_render_metrics_contains_metric_families() -> None:
    # Note: "family_probe" and operation "typing" are distinct labels so this
    # test never collides with the label values asserted by other exact-value
    # metrics tests.
    metrics.record_turn("reply", "intent")
    metrics.record_llm_usage(
        "deepseek",
        "deepseek-chat",
        "family_probe",
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    started = time.perf_counter()
    metrics.record_llm_call(
        "deepseek",
        "deepseek-chat",
        "family_probe",
        started=started,
        status="success",
        output="ok",
    )
    metrics.record_user_activity(user_id=1, chat_id=2)
    metrics.record_reply_length("reply", 100)
    metrics.record_telegram_error("typing", "flood")
    text = metrics.render_metrics().decode()
    for name in (
        "vanessa_turns_total",
        "vanessa_turn_duration_seconds",
        "vanessa_stage_duration_seconds",
        "vanessa_llm_tokens_total",
        "vanessa_llm_cost_total",
        "vanessa_llm_empty_total",
        "vanessa_llm_errors_total",
        "vanessa_rag_score",
        "vanessa_telegram_errors_total",
        "vanessa_telegram_rate_limits_total",
        "vanessa_active_users",
        "vanessa_active_sessions",
        "vanessa_reply_length_chars",
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


def test_knowledge_vault_metrics_exposed() -> None:
    metrics.record_knowledge_mutation("person", "update")
    metrics.record_knowledge_vector_sync(0.12)
    metrics.record_knowledge_search("qdrant", hits=3)
    metrics.record_knowledge_search("postgres_fts", hits=1)
    text = metrics.render_metrics().decode()
    assert "vanessa_knowledge_mutations_total" in text
    assert "vanessa_knowledge_vector_sync_duration_seconds" in text
    assert "vanessa_knowledge_search_hits_total" in text
    assert 'type="person"' in text
    assert 'action="update"' in text
    assert 'source="qdrant"' in text
    assert 'source="postgres_fts"' in text


def test_record_llm_usage_records_cost() -> None:
    metrics.llm_cost_outcomes.clear()
    metrics.record_llm_usage(
        "deepseek",
        "deepseek-chat",
        "generation",
        {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
    )
    assert metrics.llm_cost_outcomes.count() == 1
    text = metrics.render_metrics().decode()
    assert "vanessa_llm_cost_total" in text
    assert 'token_type="prompt"}' in text
    assert 'token_type="completion"}' in text
    assert 'token_type="total"}' in text


def test_record_llm_usage_records_cache_counters() -> None:
    metrics.record_llm_usage(
        "deepseek",
        "deepseek-v4-flash",
        "generation",
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "cache_hit_tokens": 90,
            "cache_miss_tokens": 10,
        },
    )
    text = metrics.render_metrics().decode()
    assert "vanessa_llm_cache_hit_tokens_total" in text
    assert "vanessa_llm_cache_miss_tokens_total" in text
    assert 'model="deepseek-v4-flash"' in text
    assert 'kind="generation"' in text


def test_estimate_llm_cost_known_and_fallback() -> None:
    # deepseek-chat: $0.27 / $1.10 per 1M tokens -> 1M+1M = $1.37.
    assert metrics.estimate_llm_cost("deepseek", "deepseek-chat", 1_000_000, 1_000_000) == pytest.approx(1.37)
    # Unlisted model falls back to the settings defaults.
    assert metrics.llm_price_per_1m("deepseek", "unknown-model") == (
        settings.llm_default_prompt_cost_per_1m,
        settings.llm_default_completion_cost_per_1m,
    )
    assert metrics.estimate_llm_cost("deepseek", "unknown-model", 0, 0) == 0.0


def test_estimate_llm_cost_applies_cache_hit_discount() -> None:
    # deepseek-v4-flash (midpoint of the published range): prompt $0.18,
    # cache-hit $0.0049, completion $0.47 per 1M.
    # 1M prompt with 900k cache-hit + 100k miss + 1M completion.
    cost = metrics.estimate_llm_cost(
        "deepseek",
        "deepseek-v4-flash",
        1_000_000,
        1_000_000,
        cache_hit_tokens=900_000,
    )
    expected = (100_000 / 1_000_000 * 0.18) + (900_000 / 1_000_000 * 0.0049) + 0.47
    assert cost == pytest.approx(expected)
    # Cache-hit price helper resolves the known model and the fallback.
    assert metrics.llm_cache_hit_prompt_price_per_1m("deepseek", "deepseek-v4-flash") == 0.0049
    assert metrics.llm_cache_hit_prompt_price_per_1m("deepseek", "deepseek-v4-pro") == 0.0128
    assert metrics.llm_cache_hit_prompt_price_per_1m("deepseek", "unknown-model") == (
        settings.llm_default_cache_hit_prompt_cost_per_1m
    )


def test_record_llm_call_empty_output() -> None:
    metrics.llm_empty_outcomes.clear()
    started = time.perf_counter()
    metrics.record_llm_call(
        "deepseek",
        "deepseek-chat",
        "generation",
        started=started,
        status="success",
        usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
        output="   ",
    )
    assert metrics.llm_empty_outcomes.count() == 1
    text = metrics.render_metrics().decode()
    assert "vanessa_llm_empty_total" in text


def test_record_llm_call_non_empty_output_not_counted() -> None:
    metrics.llm_empty_outcomes.clear()
    started = time.perf_counter()
    metrics.record_llm_call(
        "deepseek",
        "deepseek-chat",
        "generation",
        started=started,
        status="success",
        usage=None,
        output="hello",
    )
    assert metrics.llm_empty_outcomes.count() == 0


def test_record_user_activity_sets_gauges() -> None:
    metrics.active_users_1h.clear()
    metrics.active_users_24h.clear()
    metrics.active_sessions_5m.clear()
    metrics.record_user_activity(user_id=111, chat_id=999)
    metrics.record_user_activity(user_id=222, chat_id=999)
    metrics.record_user_activity(user_id=111, chat_id=888)
    text = metrics.render_metrics().decode()
    assert "vanessa_active_users" in text
    assert 'scope="1h"} 2.0' in text
    assert 'scope="24h"} 2.0' in text
    assert 'scope="5m"} 2.0' in text


def test_record_reply_length_exposed() -> None:
    metrics.record_reply_length("reply", 350)
    text = metrics.render_metrics().decode()
    assert "vanessa_reply_length_chars" in text
    assert 'action="reply"' in text


def test_record_telegram_error_rate_limit_counter() -> None:
    metrics.record_telegram_error("send_reply", "flood")
    metrics.record_telegram_error("send_reply", "blocked")
    metrics.record_telegram_error("send_reply", "network")
    text = metrics.render_metrics().decode()
    assert "vanessa_telegram_rate_limits_total" in text
    # Labels are sorted alphabetically, so error_type precedes operation here.
    # Counters accumulate across tests in this module, so only the label
    # presence (not the exact value) is asserted.
    assert 'vanessa_telegram_rate_limits_total{error_type="flood",operation="send_reply"}' in text
    assert 'vanessa_telegram_rate_limits_total{error_type="blocked",operation="send_reply"}' in text
    # network is NOT a rate-limit class -> must not feed this counter.
    assert 'vanessa_telegram_rate_limits_total{error_type="network"' not in text
