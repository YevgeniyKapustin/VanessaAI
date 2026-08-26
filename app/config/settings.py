from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    required_user_telegram_id: int = 0
    # If set (> 0), the bot only works in this single Telegram chat.
    allowed_chat_telegram_id: int = 0

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "vanessa"
    postgres_password: str = "vanessa"
    postgres_db: str = "vanessa"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "messages"
    # Dedicated collection for the semantic knowledge vault notes (People/Lore/
    # Culture/Logs) — the primary embedding search source; raw messages stay in
    # qdrant_collection as a fallback.
    qdrant_knowledge_collection: str = "knowledge"

    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    llm_provider: str = "deepseek"  # "deepseek" (default) or "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_planner_model: str = ""
    anthropic_max_tokens: int = 4096

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_planner_model: str = ""
    deepseek_max_tokens: int = 4096

    # Humor Critic (Generator–Critic pattern)
    critic_enabled: bool = False
    critic_max_iterations: int = 1
    critic_model: str = ""
    critic_apply_to_all: bool = False

    rag_context_min: int = 20
    rag_context_max: int = 50
    rag_anchor_max: int = 10
    rag_context_window_before: int = 10
    rag_context_window_after: int = 10
    rag_context_window_max_total: int = 220
    rag_hybrid_top_k: int = 20
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

    qdrant_on_disk: bool = True
    qdrant_quantization_enabled: bool = True
    qdrant_indexing_threshold: int = 20000
    qdrant_hnsw_m: int = 16
    qdrant_hnsw_ef_construct: int = 64

    db_pool_size: int = 5
    db_max_overflow: int = 2

    decision_relevance_threshold: float = 0.76
    decision_session_window_size: int = 10
    decision_rate_limit_per_minute: int = 10
    decision_bot_names: str = ""
    decision_trigger_keywords: str = ""
    decision_planner_prefilter: bool = True
    decision_post_reply_listen_count: int = 2
    decision_session_idle_seconds: int = 300

    # Directory with one YAML file per section (bot, persona, llm, ...)
    # or a single monolithic YAML file for backward compatibility.
    content_config_path: str = "config/content"
    nicknames_config_path: str = "config/nicknames.yaml"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://api:8000"
    api_internal_token: str = ""
    api_auto_create_schema: bool = False

    indexing_max_retries: int = 2
    llm_max_retries: int = 2

    log_level: str = "INFO"

    # File logging — persist logs to disk with rotation (one file per service:
    # api.log / bot.log / import.log / preflight.log). Set LOG_FILE_ENABLED=false
    # to keep console-only logging.
    log_dir: str = "logs"
    log_file_enabled: bool = True
    log_file_max_bytes: int = 5_242_880  # 5 MiB per file before rotation
    log_file_backup_count: int = 5
    # Optional; empty string falls back to LOG_LEVEL.
    log_file_level: str = ""

    obsidian_vault_path: str = ""
    obsidian_notes_subdir: str = "telegram"
    obsidian_attachments_subdir: str = "attachments"
    obsidian_git_enabled: bool = True
    obsidian_git_remote: str = "origin"
    obsidian_git_branch: str = ""
    obsidian_git_user_name: str = "VanessaAI Bot"
    obsidian_git_user_email: str = "bot@vanessa.local"

    # Knowledge vault — the bot's own machine-only structured memory.
    knowledge_path: str = "knowledge"
    knowledge_max_blocks: int = 3
    knowledge_people_max_blocks: int = 1
    knowledge_model: str = ""
    knowledge_memory_enabled: bool = True
    knowledge_memory_cooldown_seconds: int = 300
    knowledge_memory_max_tokens: int = 512
    knowledge_sweep_enabled: bool = True
    knowledge_sweep_interval_messages: int = 50
    knowledge_sweep_batch_size: int = 200
    knowledge_sweep_window_size: int = 40
    knowledge_sweep_window_overlap: int = 10
    knowledge_sweep_poll_seconds: int = 60

    # Semantic vector search over the knowledge vault (Qdrant "knowledge").
    knowledge_vector_top_k: int = 10
    knowledge_vector_min_score: float = 0.3

    # Participants digest injected into the query-composition prompt.
    knowledge_participant_max_people: int = 20
    knowledge_participant_max_facts: int = 5

    # Mood & relationship metrics (knowledge vault).
    knowledge_metrics_enabled: bool = True
    knowledge_metrics_model: str = ""
    knowledge_metrics_max_tokens: int = 768
    knowledge_metrics_cooldown_seconds: int = 900
    knowledge_metrics_history_days: int = 14

    # Behavioral feedback from metrics.
    decision_metrics_rule_enabled: bool = True
    decision_toxicity_ignore_threshold: float = 0.8
    decision_trust_ignore_threshold: float = 30.0
    feedback_tone_enabled: bool = True

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
    def resolved_critic_model(self) -> str:
        if self.critic_model.strip():
            return self.critic_model.strip()
        if self.llm_provider == "claude":
            return self.anthropic_model
        return self.deepseek_model

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
