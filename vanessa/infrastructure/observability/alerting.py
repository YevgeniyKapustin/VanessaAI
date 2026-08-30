"""In-process alert evaluation with Telegram delivery to a dev channel.

Runs in each process (api and bot) against the local rolling metric windows
(see :mod:`vanessa.infrastructure.observability.metrics`), so a broken provider, flooded Telegram
or a stalled pipeline raises an alert in seconds without extra infrastructure.
Rules are evaluated every ``ALERTING_CHECK_INTERVAL_SECONDS`` and each rule has
a cooldown (``ALERTING_COOLDOWN_SECONDS``) to prevent spam.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from vanessa.config.settings import settings
from vanessa.infrastructure.observability import metrics

logger = logging.getLogger(__name__)

_MIN_SAMPLES = 5


@dataclass(frozen=True, slots=True)
class Alert:
    rule: str
    message: str


class AlertManager:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: int,
        check_interval: float,
        cooldown: float,
        error_rate_threshold: float,
        latency_p95_threshold: float,
        rag_empty_threshold: float,
        llm_empty_threshold: float = 0.1,
        cost_window_threshold_usd: float = 5.0,
        min_samples: int = _MIN_SAMPLES,
        balance_check_hours: int = 0,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._check_interval = check_interval
        self._cooldown = cooldown
        self._error_rate_threshold = error_rate_threshold
        self._latency_p95_threshold = latency_p95_threshold
        self._rag_empty_threshold = rag_empty_threshold
        self._llm_empty_threshold = llm_empty_threshold
        self._cost_window_threshold_usd = cost_window_threshold_usd
        self._min_samples = min_samples
        self._balance_check_hours = balance_check_hours
        self._last_sent: dict[str, float] = {}
        self._last_balance_check = 0.0

    # -- rule evaluation -------------------------------------------------------
    def evaluate(self) -> list[Alert]:
        alerts: list[Alert] = []

        llm_total = metrics.llm_outcomes.count()
        if llm_total >= self._min_samples:
            rate = metrics.llm_outcomes.error_rate(lambda status: status == "error")
            if rate > self._error_rate_threshold:
                alerts.append(
                    Alert(
                        "llm_error_rate",
                        f"⚠️ LLM error rate {rate:.0%} over window "
                        f"(threshold {self._error_rate_threshold:.0%})",
                    )
                )

        # Empty/blank completions are a quality signal: the model returned
        # nothing usable. Compare against successful (non-error) calls in the
        # same window.
        llm_success = llm_total - sum(
            1 for sample in metrics.llm_outcomes.snapshot() if sample == "error"
        )
        empty_count = metrics.llm_empty_outcomes.count()
        if llm_success >= self._min_samples and empty_count and (
            empty_count / llm_success
        ) > self._llm_empty_threshold:
            alerts.append(
                Alert(
                    "llm_empty_rate",
                    f"⬜ Empty LLM output {empty_count / llm_success:.0%} of successful "
                    f"calls over window (threshold {self._llm_empty_threshold:.0%})",
                )
            )

        turn_total = metrics.turn_durations.count()
        if turn_total >= self._min_samples:
            p95 = metrics.turn_durations.percentile(95)
            if p95 is not None and p95 > self._latency_p95_threshold:
                alerts.append(
                    Alert(
                        "turn_p95",
                        f"🐢 Reply latency p95 {p95:.1f}s over window "
                        f"(threshold {self._latency_p95_threshold:.1f}s)",
                    )
                )

        rag_total = metrics.rag_outcomes.count()
        if rag_total >= self._min_samples:
            empty_rate = metrics.rag_outcomes.error_rate(
                lambda value: value[1] == 0
            )
            if empty_rate > self._rag_empty_threshold:
                alerts.append(
                    Alert(
                        "rag_empty_rate",
                        f"🔍 Empty RAG retrieval {empty_rate:.0%} over window "
                        f"(threshold {self._rag_empty_threshold:.0%})",
                    )
                )

        tg_total = metrics.telegram_outcomes.count()
        if tg_total >= self._min_samples:
            tg_error_rate = metrics.telegram_outcomes.error_rate(
                lambda value: value[1] == "error"
            )
            if tg_error_rate > self._error_rate_threshold:
                alerts.append(
                    Alert(
                        "telegram_error_rate",
                        f"📡 Telegram error rate {tg_error_rate:.0%} over window "
                        f"(threshold {self._error_rate_threshold:.0%})",
                    )
                )

        # A single flood/429 or blocked-by-user error is already actionable —
        # it usually means the bot is spamming or was blocked by a user.
        if metrics.telegram_limit_outcomes.count() > 0:
            alerts.append(
                Alert(
                    "telegram_flood",
                    "🚫 Telegram rate-limit (429) or blocked-by-user errors in window",
                )
            )

        # Estimated spend over the window catches runaway loops and spam bursts.
        cost_total = sum(metrics.llm_cost_outcomes.snapshot())
        if cost_total > self._cost_window_threshold_usd:
            alerts.append(
                Alert(
                    "llm_cost_spike",
                    f"💸 LLM spend ${cost_total:.2f} in window "
                    f"(threshold ${self._cost_window_threshold_usd:.2f})",
                )
            )

        queue = metrics.queue_length()
        if queue:
            alerts.append(Alert("background_queue", f"📥 Background queue backlog: {queue}"))

        return alerts

    async def check_balance(self) -> list[Alert]:
        """Probe the DeepSeek provider for an insufficient-balance (HTTP 402)."""
        if self._balance_check_hours <= 0:
            return []
        now = time.time()
        if now - self._last_balance_check < self._balance_check_hours * 3600:
            return []
        self._last_balance_check = now
        if settings.llm_provider == "claude" or not settings.deepseek_api_key:
            return []
        url = f"{settings.deepseek_base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("balance_check_failed: %s", exc)
            return []
        if response.status_code == 402:
            return [Alert("llm_balance", "💸 LLM provider: insufficient balance (HTTP 402)")]
        return []

    # -- delivery --------------------------------------------------------------
    def _cooldown_ok(self, rule: str) -> bool:
        last = self._last_sent.get(rule, 0.0)
        return time.time() - last >= self._cooldown

    async def _send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "disable_notification": False,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("alert_send_failed chat_id=%s error=%s", self._chat_id, exc)

    async def check_and_alert(self) -> list[str]:
        """Evaluate rules, send new alerts, return the rules that fired."""
        alerts = self.evaluate()
        alerts.extend(await self.check_balance())
        fired: list[str] = []
        for alert in alerts:
            if not self._cooldown_ok(alert.rule):
                continue
            self._last_sent[alert.rule] = time.time()
            logger.warning("alert rule=%s message=%s", alert.rule, alert.message)
            await self._send(f"[{alert.rule}] {alert.message}")
            fired.append(alert.rule)
        return fired

    async def run_forever(self) -> None:
        """Periodic alert loop (cancel to stop)."""
        while True:
            try:
                await self.check_and_alert()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("alert_check_failed")
            await asyncio.sleep(self._check_interval)


def create_alert_manager() -> AlertManager | None:
    """Build an AlertManager from settings, or None when disabled/misconfigured."""
    if not settings.alerting_enabled:
        return None
    if not settings.telegram_bot_token or not settings.alerting_dev_chat_id:
        return None
    return AlertManager(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.alerting_dev_chat_id,
        check_interval=settings.alerting_check_interval_seconds,
        cooldown=settings.alerting_cooldown_seconds,
        error_rate_threshold=settings.alerting_error_rate_threshold,
        latency_p95_threshold=settings.alerting_latency_p95_threshold,
        rag_empty_threshold=settings.alerting_rag_empty_threshold,
        llm_empty_threshold=settings.alerting_llm_empty_threshold,
        cost_window_threshold_usd=settings.alerting_cost_window_threshold_usd,
        balance_check_hours=settings.alerting_balance_check_hours,
    )
