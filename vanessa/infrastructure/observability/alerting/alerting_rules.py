from __future__ import annotations

from dataclasses import dataclass

from vanessa.infrastructure.observability import metrics


@dataclass(frozen=True, slots=True)
class Alert:
    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class _RuleConfig:
    min_samples: int
    error_rate_threshold: float
    llm_empty_threshold: float
    latency_p95_threshold: float
    rag_empty_threshold: float
    cost_window_threshold_usd: float


def evaluate_alert_rules(
    *,
    min_samples: int,
    error_rate_threshold: float,
    llm_empty_threshold: float,
    latency_p95_threshold: float,
    rag_empty_threshold: float,
    cost_window_threshold_usd: float,
) -> list[Alert]:
    config = _RuleConfig(
        min_samples=min_samples,
        error_rate_threshold=error_rate_threshold,
        llm_empty_threshold=llm_empty_threshold,
        latency_p95_threshold=latency_p95_threshold,
        rag_empty_threshold=rag_empty_threshold,
        cost_window_threshold_usd=cost_window_threshold_usd,
    )
    return [
        *_llm_alerts(config),
        *_platform_alerts(config),
        *_channel_alerts(config),
    ]


def _llm_alerts(config: _RuleConfig) -> list[Alert]:
    alerts: list[Alert] = []
    llm_total = metrics.llm_outcomes.count()
    if llm_total >= config.min_samples:
        rate = metrics.llm_outcomes.error_rate(lambda status: status == "error")
        if rate > config.error_rate_threshold:
            alerts.append(
                Alert(
                    "llm_error_rate",
                    f"⚠️ LLM error rate {rate:.0%} over window "
                    f"(threshold {config.error_rate_threshold:.0%})",
                )
            )

    llm_success = llm_total - sum(
        1 for sample in metrics.llm_outcomes.snapshot() if sample == "error"
    )
    empty_count = metrics.llm_empty_outcomes.count()
    if llm_success >= config.min_samples and empty_count and (
        empty_count / llm_success
    ) > config.llm_empty_threshold:
        alerts.append(
            Alert(
                "llm_empty_rate",
                f"⬜ Empty LLM output {empty_count / llm_success:.0%} of successful "
                f"calls over window (threshold {config.llm_empty_threshold:.0%})",
            )
        )
    return alerts


def _present(*alerts: Alert | None) -> list[Alert]:
    return [alert for alert in alerts if alert is not None]


def _turn_p95_alert(config: _RuleConfig) -> Alert | None:
    if metrics.turn_durations.count() < config.min_samples:
        return None
    p95 = metrics.turn_durations.percentile(95)
    if p95 is None or p95 <= config.latency_p95_threshold:
        return None
    return Alert(
        "turn_p95",
        f"🐢 Reply latency p95 {p95:.1f}s over window "
        f"(threshold {config.latency_p95_threshold:.1f}s)",
    )


def _rag_empty_alert(config: _RuleConfig) -> Alert | None:
    if metrics.rag_outcomes.count() < config.min_samples:
        return None
    empty_rate = metrics.rag_outcomes.error_rate(lambda value: value[1] == 0)
    if empty_rate <= config.rag_empty_threshold:
        return None
    return Alert(
        "rag_empty_rate",
        f"🔍 Empty RAG retrieval {empty_rate:.0%} over window "
        f"(threshold {config.rag_empty_threshold:.0%})",
    )


def _platform_alerts(config: _RuleConfig) -> list[Alert]:
    return _present(_turn_p95_alert(config), _rag_empty_alert(config))


def _telegram_error_alert(config: _RuleConfig) -> Alert | None:
    if metrics.telegram_outcomes.count() < config.min_samples:
        return None
    tg_error_rate = metrics.telegram_outcomes.error_rate(
        lambda value: value[1] == "error"
    )
    if tg_error_rate <= config.error_rate_threshold:
        return None
    return Alert(
        "telegram_error_rate",
        f"📡 Telegram error rate {tg_error_rate:.0%} over window "
        f"(threshold {config.error_rate_threshold:.0%})",
    )


def _telegram_flood_alert() -> Alert | None:
    if metrics.telegram_limit_outcomes.count() <= 0:
        return None
    return Alert(
        "telegram_flood",
        "🚫 Telegram rate-limit (429) or blocked-by-user errors in window",
    )


def _cost_spike_alert(config: _RuleConfig) -> Alert | None:
    cost_total = sum(metrics.llm_cost_outcomes.snapshot())
    if cost_total <= config.cost_window_threshold_usd:
        return None
    return Alert(
        "llm_cost_spike",
        f"💸 LLM spend ${cost_total:.2f} in window "
        f"(threshold ${config.cost_window_threshold_usd:.2f})",
    )


def _queue_alert() -> Alert | None:
    queue = metrics.queue_length()
    if not queue:
        return None
    return Alert("background_queue", f"📥 Background queue backlog: {queue}")


def _channel_alerts(config: _RuleConfig) -> list[Alert]:
    return _present(
        _telegram_error_alert(config),
        _telegram_flood_alert(),
        _cost_spike_alert(config),
        _queue_alert(),
    )
