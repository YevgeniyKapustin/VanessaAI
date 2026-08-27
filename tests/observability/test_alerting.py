import asyncio
import time

from app.observability import metrics
from app.observability.alerting import AlertManager


def _manager(**overrides) -> AlertManager:
    defaults = dict(
        bot_token="t",
        chat_id=1,
        check_interval=60,
        cooldown=0,
        error_rate_threshold=0.05,
        latency_p95_threshold=7.0,
        rag_empty_threshold=0.5,
        min_samples=5,
    )
    defaults.update(overrides)
    return AlertManager(**defaults)


def test_evaluate_llm_error_rate(monkeypatch) -> None:
    window = metrics.EventWindow(window_seconds=300)
    for _ in range(4):
        window.add("error")
    for _ in range(4):
        window.add("success")
    monkeypatch.setattr(metrics, "llm_outcomes", window)
    alerts = _manager().evaluate()
    assert any(alert.rule == "llm_error_rate" for alert in alerts)


def test_evaluate_latency_p95(monkeypatch) -> None:
    window = metrics.EventWindow(window_seconds=300)
    for _ in range(10):
        window.add(8.0)
    monkeypatch.setattr(metrics, "turn_durations", window)
    alerts = _manager(latency_p95_threshold=7.0).evaluate()
    assert any(alert.rule == "turn_p95" for alert in alerts)


def test_evaluate_rag_empty_rate(monkeypatch) -> None:
    window = metrics.EventWindow(window_seconds=300)
    for _ in range(6):
        window.add(("semantic", 0))
    for _ in range(4):
        window.add(("semantic", 3))
    monkeypatch.setattr(metrics, "rag_outcomes", window)
    alerts = _manager(rag_empty_threshold=0.5).evaluate()
    assert any(alert.rule == "rag_empty_rate" for alert in alerts)


def test_evaluate_telegram_error_rate(monkeypatch) -> None:
    window = metrics.EventWindow(window_seconds=300)
    for _ in range(4):
        window.add(("typing", "error"))
    for _ in range(4):
        window.add(("send_reply", "success"))
    monkeypatch.setattr(metrics, "telegram_outcomes", window)
    alerts = _manager().evaluate()
    assert any(alert.rule == "telegram_error_rate" for alert in alerts)


def _patch_all_windows(monkeypatch) -> None:
    """Isolate every alerting window so prior tests can't skew the outcome."""
    for name in (
        "llm_outcomes",
        "llm_empty_outcomes",
        "llm_cost_outcomes",
        "turn_durations",
        "rag_outcomes",
        "telegram_outcomes",
        "telegram_limit_outcomes",
    ):
        monkeypatch.setattr(metrics, name, metrics.EventWindow(window_seconds=300))


def test_no_alert_below_min_samples(monkeypatch) -> None:
    _patch_all_windows(monkeypatch)
    window = metrics.EventWindow(window_seconds=300)
    window.add("error")
    monkeypatch.setattr(metrics, "llm_outcomes", window)
    assert _manager().evaluate() == []


def test_cooldown_suppresses_resend() -> None:
    manager = _manager(cooldown=600)
    manager._last_sent["x"] = time.time()
    assert manager._cooldown_ok("x") is False
    assert manager._cooldown_ok("y") is True


def test_evaluate_empty_llm_rate(monkeypatch) -> None:
    _patch_all_windows(monkeypatch)
    llm_window = metrics.EventWindow(window_seconds=300)
    for _ in range(8):
        llm_window.add("success")
    monkeypatch.setattr(metrics, "llm_outcomes", llm_window)
    empty_window = metrics.EventWindow(window_seconds=300)
    for _ in range(3):
        empty_window.add(1)
    monkeypatch.setattr(metrics, "llm_empty_outcomes", empty_window)
    alerts = _manager(llm_empty_threshold=0.1).evaluate()
    assert any(alert.rule == "llm_empty_rate" for alert in alerts)


def test_evaluate_telegram_flood(monkeypatch) -> None:
    _patch_all_windows(monkeypatch)
    metrics.telegram_limit_outcomes.add(("send_reply", "flood"))
    alerts = _manager().evaluate()
    assert any(alert.rule == "telegram_flood" for alert in alerts)


def test_evaluate_cost_spike(monkeypatch) -> None:
    _patch_all_windows(monkeypatch)
    metrics.llm_cost_outcomes.add(6.0)
    alerts = _manager(cost_window_threshold_usd=5.0).evaluate()
    assert any(alert.rule == "llm_cost_spike" for alert in alerts)


def test_check_and_alert_sends_only_new_alerts(monkeypatch) -> None:
    _patch_all_windows(monkeypatch)
    window = metrics.EventWindow(window_seconds=300)
    for _ in range(6):
        window.add("error")
    monkeypatch.setattr(metrics, "llm_outcomes", window)

    manager = _manager(cooldown=600)
    sent: list[str] = []

    async def fake_send(message: str) -> None:
        sent.append(message)

    manager._send = fake_send  # type: ignore[method-assign]

    fired = asyncio.run(manager.check_and_alert())
    assert "llm_error_rate" in fired
    assert sent and "llm_error_rate" in sent[0]

    # Cooldown now active -> the rule does not fire again immediately.
    fired_again = asyncio.run(manager.check_and_alert())
    assert "llm_error_rate" not in fired_again
    assert len(sent) == 1
