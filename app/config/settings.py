from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    required_user_telegram_id: int = 0

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "vanessa"
    postgres_password: str = "vanessa"
    postgres_db: str = "vanessa"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "messages"

    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 4096

    rag_context_min: int = 20
    rag_context_max: int = 50
    rag_anchor_max: int = 10
    rag_context_window_before: int = 10
    rag_context_window_after: int = 10
    rag_context_window_max_total: int = 220
    rag_hybrid_top_k: int = 20
    rag_humor_top_k: int = 15
    rag_humor_anchor_max: int = 5
    rag_humor_max_quotes: int = 3
    rag_humor_min_quote_score: float = 2.5
    rag_humor_window_before: int = 8
    rag_humor_window_after: int = 4
    rag_embed_cache_size: int = 256
    rag_embed_max_chars: int = 2000
    rag_query_rewrite_use_llm: bool = True
    rag_query_rewrite_max_tokens: int = 256
    rag_vector_min_score: float = 0.35

    qdrant_on_disk: bool = True
    qdrant_quantization_enabled: bool = True
    qdrant_indexing_threshold: int = 20000
    qdrant_hnsw_m: int = 16
    qdrant_hnsw_ef_construct: int = 64

    db_pool_size: int = 5
    db_max_overflow: int = 2

    decision_relevance_threshold: float = 0.75
    decision_session_window_size: int = 10
    decision_rate_limit_per_minute: int = 10
    decision_bot_names: str = ""
    decision_trigger_keywords: str = ""
    decision_planner_prefilter: bool = True
    decision_post_reply_listen_count: int = 5

    content_config_path: str = "config/content.yaml"
    nicknames_config_path: str = "config/nicknames.yaml"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://api:8000"
    api_internal_token: str = ""
    api_auto_create_schema: bool = False

    indexing_max_retries: int = 2
    llm_max_retries: int = 2

    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

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


settings = Settings()
