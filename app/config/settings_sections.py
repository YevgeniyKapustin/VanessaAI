"""Per-service settings sections over a shared base.

The monolithic ``Settings`` aggregate (``app.config.settings``) is composed
from these mixins so every service can eventually load only what it needs
(``BotSettings``, ``CoreSettings``, ``WorkerSettings``, ``McpSettings``)
while sharing the common infra wiring (DB, broker, logging, metrics). Secrets
stay env-driven only — no YAML ever holds a token.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedSettings(BaseSettings):
    """Common infrastructure settings every service needs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Postgres ------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "vanessa"
    postgres_password: str = "vanessa"
    postgres_db: str = "vanessa"

    # --- Qdrant --------------------------------------------------------------
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "messages"
    # Dedicated collection for the semantic knowledge vault notes.
    qdrant_knowledge_collection: str = "knowledge"
    qdrant_on_disk: bool = True
    qdrant_quantization_enabled: bool = True
    qdrant_indexing_threshold: int = 20000
    qdrant_hnsw_m: int = 16
    qdrant_hnsw_ef_construct: int = 64

    db_pool_size: int = 5
    db_max_overflow: int = 2

    # --- Config paths ----------------------------------------------------------
    # Directory with one YAML file per section (bot, persona, llm, ...) or a
    # single monolithic YAML file for backward compatibility.
    content_config_path: str = "config/content"
    nicknames_config_path: str = "config/nicknames.yaml"

    # --- API ----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://api:8000"
    api_internal_token: str = ""
    api_auto_create_schema: bool = False

    # --- Logging -------------------------------------------------------------
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file_enabled: bool = True
    log_file_max_bytes: int = 5_242_880  # 5 MiB per file before rotation
    log_file_backup_count: int = 5
    log_file_level: str = ""  # empty falls back to LOG_LEVEL

    # --- Prometheus ----------------------------------------------------------
    metrics_enabled: bool = True
    metrics_require_token: bool = False

    # --- Transport / broker (async service decoupling) ------------------------
    # How the bot talks to the agent core: "http" (legacy /api/v1/chat) or
    # "redis" (Redis Streams RPC over the broker).
    transport: str = "http"
    # Dedicated Redis DB index for broker streams (DB 0 is used by Langfuse).
    broker_redis_url: str = "redis://localhost:6379/1"
    # Prefix for stream names (turns / replies / tasks / dlq).
    broker_streams_prefix: str = "vanessa"
    # RPC reply timeout for the bot → agent-core turn round-trip.
    broker_rpc_timeout_seconds: float = 120.0
    # Poll interval (s) for non-blocking consumer loops.
    broker_poll_seconds: float = 0.05
    broker_dlq_enabled: bool = True
    broker_stream_maxlen: int = 100_000
    # Consumer group names (one group per logical consumer service).
    broker_group_agent_core: str = "agent-core"
    broker_group_worker: str = "worker"
    # Stable consumer id suffix; empty → a per-process uuid is generated.
    broker_consumer_id: str = ""

    # --- Transactional outbox ------------------------------------------------
    outbox_enabled: bool = True
    outbox_poll_seconds: float = 1.0
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 5

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


class BotMixin:
    """Telegram transport service settings."""

    telegram_bot_token: str = ""
    required_user_telegram_id: int = 0
    # If set (> 0), the bot only works in this single Telegram chat.
    allowed_chat_telegram_id: int = 0

    # HTTP timeouts for the legacy bot → API /api/v1/chat call (2-6s+ pipeline).
    api_client_read_timeout: float = 120.0
    api_client_connect_timeout: float = 10.0

    bot_typing_interval_seconds: float = 4.0
    bot_message_delay_seconds: float = 0.7
    bot_max_messages: int = 8

    # Port for the bot process Prometheus HTTP endpoint.
    bot_metrics_port: int = 9101

    # --- Obsidian notes -------------------------------------------------------
    obsidian_vault_path: str = ""
    obsidian_notes_subdir: str = "telegram"
    obsidian_attachments_subdir: str = "attachments"
    obsidian_git_enabled: bool = True
    obsidian_git_remote: str = "origin"
    obsidian_git_branch: str = ""
    obsidian_git_user_name: str = "VanessaAI Bot"
    obsidian_git_user_email: str = "bot@vanessa.local"


class CoreMixin:
    """Agent-core (orchestrator) settings: LLM, RAG, decision, vision, tools."""

    # --- Embeddings ----------------------------------------------------------
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    embedding_threads: int = 1
    hf_token: str = ""

    # --- LLM providers -------------------------------------------------------
    llm_provider: str = "deepseek"  # "deepseek" (default) or "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_planner_model: str = ""
    anthropic_max_tokens: int = 4096

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_planner_model: str = "deepseek-chat"
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_max_tokens: int = 4096

    # --- Vision (DeepSeek multimodal) ----------------------------------------
    vision_enabled: bool = True
    deepseek_vision_model: str = "deepseek-v4-flash-vision-exp"
    vision_max_image_bytes: int = 1_500_000
    vision_session_images: int = 2
    vision_max_images_per_turn: int = 2
    vision_photo_placeholder: str = "[фото]"
    vision_reply_to_any_photo: bool = False
    vision_media_group_debounce_seconds: float = 1.5
    vision_media_group_max_photos: int = 10
    vision_photo_candidates: int = 5
    vision_photo_caption_enabled: bool = True
    vision_photo_caption_model: str = ""
    vision_photo_caption_max_chars: int = 160

    # --- RAG ------------------------------------------------------------------
    rag_context_min: int = 20
    rag_context_max: int = 50
    rag_anchor_max: int = 16
    rag_context_window_before: int = 10
    rag_context_window_after: int = 10
    rag_context_window_max_total: int = 360
    rag_hybrid_top_k: int = 40
    rag_humor_top_k: int = 15
    rag_humor_anchor_max: int = 5
    rag_humor_max_quotes: int = 2
    rag_humor_min_quote_score: float = 2.5
    rag_humor_window_before: int = 8
    rag_humor_window_after: int = 4
    rag_embed_cache_size: int = 256
    rag_embed_max_chars: int = 2000
    rag_query_rewrite_use_llm: bool = True
    rag_query_rewrite_max_tokens: int = 256
    rag_react_max_steps: int = 3
    rag_react_min_blocks: int = 2
    rag_vector_min_score: float = 0.35

    # --- Decision engine ------------------------------------------------------
    decision_relevance_threshold: float = 0.76
    decision_session_window_size: int = 10
    decision_rate_limit_per_minute: int = 10
    decision_bot_names: str = ""
    decision_trigger_keywords: str = ""
    decision_planner_prefilter: bool = True
    decision_prefilter_defer_questions: bool = True
    decision_post_reply_listen_count: int = 4
    decision_session_idle_seconds: int = 300
    decision_compose_refuse_enabled: bool = True
    decision_reaction_gate_enabled: bool = True
    decision_reaction_gate_model: str = ""
    decision_reaction_gate_max_tokens: int = 5
    decision_reaction_gate_recent_window: int = 4
    decision_reaction_gate_heuristics_enabled: bool = True
    decision_reaction_gate_bypass_reply_to_bot: bool = True
    decision_reaction_gate_bypass_listen_window: bool = True
    decision_continuation_follow_up_enabled: bool = True
    decision_metrics_rule_enabled: bool = True
    decision_toxicity_ignore_threshold: float = 0.8
    decision_trust_ignore_threshold: float = 30.0
    feedback_tone_enabled: bool = True
    decision_low_attitude_rule_enabled: bool = True
    decision_annoyance_ignore_threshold: float = 0.6
    decision_low_attitude_trust_threshold: float = 25.0
    decision_low_attitude_sympathy_threshold: float = -0.3
    decision_loop_window: int = 10
    decision_loop_similarity_threshold: float = 0.4
    decision_loop_decay_half_life_seconds: int = 3600
    feedback_annoyance_threshold: float = 0.5

    # --- Knowledge vault (read/retrieval side) --------------------------------
    knowledge_path: str = "knowledge"
    knowledge_max_blocks: int = 3
    knowledge_people_max_blocks: int = 3
    knowledge_model: str = ""
    knowledge_vector_top_k: int = 10
    knowledge_vector_min_score: float = 0.3
    knowledge_participant_max_people: int = 10
    knowledge_participant_max_facts: int = 3
    knowledge_participant_recent_window: int = 5
    knowledge_participant_min_people: int = 3
    knowledge_people_raw_max_chars: int = 1400
    knowledge_people_chunks_enabled: bool = True
    knowledge_people_chunk_chars: int = 600
    knowledge_people_chunk_overlap: int = 120
    knowledge_people_detail_blocks: int = 5
    compose_budget_enabled: bool = True

    # --- Web search -----------------------------------------------------------
    web_search_enabled: bool = False
    web_search_provider: str = "tavily"
    web_search_api_key: str = ""
    web_search_max_results: int = 5
    web_search_timeout_seconds: float = 5.0
    web_search_snippet_max_chars: int = 300

    # --- Observability: LLM cost ----------------------------------------------
    llm_default_prompt_cost_per_1m: float = 0.27
    llm_default_completion_cost_per_1m: float = 1.10
    llm_default_cache_hit_prompt_cost_per_1m: float = 0.07

    # --- Langfuse tracing -----------------------------------------------------
    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_sample_rate: float = 1.0
    langfuse_id_salt: str = "vanessa"
    langfuse_flush_interval: int = 30

    # --- RAG Triad evaluation -------------------------------------------------
    rag_eval_enabled: bool = False
    rag_eval_sample_rate: float = 0.05
    rag_eval_model: str = ""

    # --- Alerting -------------------------------------------------------------
    alerting_enabled: bool = False
    alerting_check_interval_seconds: int = 60
    alerting_cooldown_seconds: int = 600
    alerting_window_seconds: int = 300
    alerting_error_rate_threshold: float = 0.05
    alerting_latency_p95_threshold: float = 7.0
    alerting_rag_empty_threshold: float = 0.5
    alerting_llm_empty_threshold: float = 0.1
    alerting_cost_window_threshold_usd: float = 5.0
    alerting_dev_chat_id: int = 0
    alerting_balance_check_hours: int = 24

    @property
    def planner_model(self) -> str:
        if self.llm_provider == "claude":
            if self.anthropic_planner_model.strip():
                return self.anthropic_planner_model.strip()
            return self.anthropic_model
        if self.deepseek_planner_model.strip():
            return self.deepseek_planner_model.strip()
        return self.deepseek_model

    @property
    def bot_name_aliases(self) -> tuple[str, ...]:
        if not self.decision_bot_names.strip():
            return ()
        return tuple(
            name.strip()
            for name in self.decision_bot_names.split(",")
            if name.strip()
        )

    @property
    def trigger_keywords(self) -> tuple[str, ...]:
        return tuple(
            word.strip()
            for word in self.decision_trigger_keywords.split(",")
            if word.strip()
        )


class WorkerMixin:
    """Background worker settings: sweep, portraits, memory, metrics, indexing."""

    indexing_max_retries: int = 2
    llm_max_retries: int = 2

    background_queue_size: int = 200
    background_workers: int = 2

    # Route post-reply background work (message indexing) and the sweep/portrait
    # loops through the broker to the dedicated worker container instead of the
    # in-process executor. Default off → everything stays in-process as before.
    worker_enabled: bool = False
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
    mcp_obsidian_url: str = ""
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
