"""Per-service settings sections over a shared base.

The monolithic ``Settings`` aggregate (``vanessa.config.settings``) is composed
from these mixins so every service can eventually load only what it needs
(``BotSettings``, ``CoreSettings``, ``WorkerSettings``, ``McpSettings``)
while sharing the common infra wiring (DB, broker, logging, metrics). Secrets
stay env-driven only — no YAML ever holds a token.
"""

from __future__ import annotations

from vanessa.config.settings_core import CoreMixin
from vanessa.config.settings_shared import SharedSettings


class BotMixin:
    """Telegram transport service settings."""

    telegram_bot_token: str = ""
    required_user_telegram_id: int = 0
    # If set (> 0), the bot only works in this single Telegram chat.
    allowed_chat_telegram_id: int = 0

    bot_typing_interval_seconds: float = 4.0
    bot_message_delay_seconds: float = 0.7
    bot_max_messages: int = 8

    # Telegram TTS stays off unless channel YAML or env flips it.
    speech_enabled: bool = False
    speech_send: str = "voice_and_text"

    # Port for the bot process Prometheus HTTP endpoint.
    bot_metrics_port: int = 9101


class WorkerMixin:
    """Background worker settings: sweep, portraits, memory, metrics."""

    llm_max_retries: int = 2

    background_queue_size: int = 200
    background_workers: int = 2

    # Route post-reply work and sweep/portrait loops to the worker process.
    worker_enabled: bool = True
    # Prometheus endpoint port for the worker process.
    worker_metrics_port: int = 9102

    # --- Knowledge memory extraction ------------------------------------------
    knowledge_memory_enabled: bool = True
    knowledge_memory_cooldown_seconds: int = 300
    knowledge_memory_max_tokens: int = 512
    knowledge_memory_prefilter_enabled: bool = True
    knowledge_memory_prefilter_min_messages: int = 1
    knowledge_memory_prefilter_min_content_chars: int = 40
    knowledge_memory_prefilter_score_threshold: float = 1.5

    # --- Sweep ----------------------------------------------------------------
    knowledge_sweep_enabled: bool = True
    knowledge_sweep_interval_messages: int = 50
    knowledge_sweep_batch_size: int = 200
    knowledge_sweep_window_size: int = 40
    knowledge_sweep_window_overlap: int = 10
    knowledge_sweep_poll_seconds: int = 60

    # --- Mood & relationship metrics ------------------------------------------
    knowledge_metrics_enabled: bool = True
    knowledge_metrics_model: str = ""
    knowledge_metrics_max_tokens: int = 768
    knowledge_metrics_cooldown_seconds: int = 900
    knowledge_metrics_history_days: int = 14

    # --- Portraits ------------------------------------------------------------
    knowledge_portrait_enabled: bool = True
    knowledge_portrait_model: str = ""
    knowledge_portrait_max_tokens: int = 384
    knowledge_portrait_poll_seconds: int = 300
    knowledge_portrait_max_chars: int = 4000


class McpMixin:
    """External MCP server endpoints (SSE) used by the agent core as a client."""

    mcp_knowledge_url: str = ""
    mcp_websearch_url: str = ""
    mcp_vision_url: str = ""
    mcp_timeout_seconds: float = 10.0
    mcp_retries: int = 2
    # Fail open: an unreachable MCP server degrades the turn instead of blocking
    # it (bounded timeouts + circuit breaker on the client side).
    mcp_fail_open: bool = True


# --- Per-service concrete settings --------------------------------------------

class BotSettings(BotMixin, SharedSettings):
    """Telegram transport service settings."""


class CoreSettings(CoreMixin, SharedSettings):
    """Agent-core service settings."""


class WorkerSettings(WorkerMixin, SharedSettings):
    """Background worker service settings."""


class McpSettings(McpMixin, SharedSettings):
    """MCP-client settings for the agent core."""
