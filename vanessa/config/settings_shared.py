"""Common infrastructure settings every service needs."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedSettings(BaseSettings):
    """Common infrastructure settings every service needs."""

    model_config = SettingsConfigDict(
        env_file=(".env.defaults", ".env.local", ".env"),
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

    # --- HTTP (health / metrics on the agent process) ------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_internal_token: str = ""
    api_auto_create_schema: bool = False

    # --- Logging -------------------------------------------------------------
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_json: bool = False
    log_file_enabled: bool = True
    log_file_max_bytes: int = 5_242_880  # 5 MiB per file before rotation
    log_file_backup_count: int = 5
    log_file_level: str = ""  # empty falls back to LOG_LEVEL

    # --- Prometheus ----------------------------------------------------------
    metrics_enabled: bool = True
    metrics_require_token: bool = False

    # --- Broker (Redis Streams RPC for turns) --------------------------------
    # Dedicated Redis DB index for broker streams (DB 0 is used by Langfuse).
    broker_redis_url: str = "redis://localhost:6379/1"
    # Prefix for stream names (turns / replies / tasks / dlq).
    broker_streams_prefix: str = "vanessa"
    # RPC reply timeout for the bot → agent turn round-trip.
    broker_rpc_timeout_seconds: float = 120.0
    # Poll interval (s) for non-blocking consumer loops.
    broker_poll_seconds: float = 0.05
    broker_dlq_enabled: bool = True
    broker_stream_maxlen: int = 100_000
    # Consumer group names (one group per logical consumer service).
    broker_group_agent: str = "agent"
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
