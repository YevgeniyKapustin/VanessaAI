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

import httpx

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.alerting.alerting_rules import (
    Alert,
    evaluate_alert_rules,
)

logger = logging.getLogger(__name__)

_HTTP_PAYMENT_REQUIRED = 402
_MIN_SAMPLES = 5


def _deepseek_probe() -> tuple[str, dict[str, str]] | None:
    if settings.llm_provider == "claude" or not settings.deepseek_api_key:
        return None
    url = f"{settings.deepseek_base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
    return url, headers


async def _probe_llm_balance(url: str, headers: dict[str, str]) -> list[Alert]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("balance_check_failed: %s", exc)
        return []
    if response.status_code == _HTTP_PAYMENT_REQUIRED:
        return [
            Alert(
                "llm_balance",
                "💸 LLM provider: insufficient balance (HTTP 402)",
            )
        ]
    return []


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
        self._llm_empty_threshold = llm_empty_threshold
        self._cost_window_threshold_usd = cost_window_threshold_usd
        self._min_samples = min_samples
        self._balance_check_hours = balance_check_hours
        self._last_sent: dict[str, float] = {}
        self._last_balance_check = 0.0

    def evaluate(self) -> list[Alert]:
        return evaluate_alert_rules(
            min_samples=self._min_samples,
            error_rate_threshold=self._error_rate_threshold,
            llm_empty_threshold=self._llm_empty_threshold,
            latency_p95_threshold=self._latency_p95_threshold,
            cost_window_threshold_usd=self._cost_window_threshold_usd,
        )

    def _balance_check_due(self, now: float) -> bool:
        if self._balance_check_hours <= 0:
            return False
        return now - self._last_balance_check >= self._balance_check_hours * 3600

    async def check_balance(self) -> list[Alert]:
        """Probe the DeepSeek provider for an insufficient-balance (HTTP 402)."""
        now = time.time()
        if not self._balance_check_due(now):
            return []
        self._last_balance_check = now
        probe = _deepseek_probe()
        if probe is None:
            return []
        url, headers = probe
        return await _probe_llm_balance(url, headers)

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
        llm_empty_threshold=settings.alerting_llm_empty_threshold,
        cost_window_threshold_usd=settings.alerting_cost_window_threshold_usd,
        balance_check_hours=settings.alerting_balance_check_hours,
    )
