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

    db_pool_size: int = 5
    db_max_overflow: int = 2

    # --- Config paths (one git tree: config/) --------------------------------
    # Loaders try cwd, then the repo root. Empty slice path → `{config_root}/…`.
    # behavior/ + channels/ — agent/bot/worker. nicknames + joins — agent.
    # presence/avatar.yaml — host process only (not compose / k8s).
    config_root: str = "config"
    behavior_config_path: str = "config/behavior"
    channels_config_path: str = "config/channels"
    nicknames_config_path: str = "config/nicknames.yaml"
    joins_config_path: str = "config/joins.yaml"
    presence_avatar_path: str = "config/presence/avatar.yaml"

    # --- Speech (ElevenLabs TTS in adapters; wav never on Redis) -----------
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "pcm_24000"
    elevenlabs_timeout_seconds: float = 30.0

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
