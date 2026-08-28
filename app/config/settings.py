import os

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
    # Dedicated thread pool size for CPU-bound SentenceTransformer inference.
    # Kept small (default 1) because inference is already serialized by an
    # asyncio lock; the pool just isolates embedding work from the default
    # asyncio thread pool so it never starves other to_thread callers.
    embedding_threads: int = 1
    # Hugging Face access token — authenticates the sentence-transformers model
    # download from the HF Hub (higher rate limits / faster downloads). Pushed
    # into os.environ below because huggingface_hub reads HF_TOKEN from there.
    hf_token: str = ""

    llm_provider: str = "deepseek"  # "deepseek" (default) or "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_planner_model: str = ""
    anthropic_max_tokens: int = 4096

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # Compose (generation) model. V4-flash is the default for standard replies,
    # dialogues and RAG answers; complex turns (coding / deep synthesis) are
    # routed to ``deepseek_pro_model`` via the gate's ``uses_pro_model`` flag.
    deepseek_model: str = "deepseek-v4-flash"
    # Gate/planner model — fast routing, intent classification, strict JSON.
    # Kept on the NON-reasoning model (deepseek-chat): the V4 models are
    # reasoning (thinking) models that, on structured/JSON planner prompts with
    # the small max_tokens budgets used below, spend the whole budget on
    # reasoning_content and return EMPTY content (finish_reason=length). The
    # gate planner and the knowledge planners (memory/metrics/portrait) all
    # resolve through this setting, so keep it on a non-reasoning model unless
    # V4 reasoning is explicitly wanted. reasoning_effort stays off (default
    # normal mode): the planner never sends it.
    deepseek_planner_model: str = "deepseek-chat"
    # Upscaled compose model for super-complex synthesis / coding turns.
    deepseek_pro_model: str = "deepseek-v4-pro"
    deepseek_max_tokens: int = 4096

    # --- Vision (DeepSeek multimodal) ------------------------------------------
    # Master switch for image understanding. When off, photo turns fall back to
    # today's behavior (caption treated as a normal text message, image ignored).
    vision_enabled: bool = True
    # Compose model used when a turn carries an image. The Exp (experimental)
    # Flash vision model is cheap (~384 tokens/image, auto-resized to ~800x800).
    deepseek_vision_model: str = "deepseek-v4-flash-vision-exp"
    # Pick the largest Telegram photo size whose file_size fits this cap; base64
    # encoding adds ~33% on top of the raw bytes. Keeps API bodies and the DB
    # attachment column bounded.
    vision_max_image_bytes: int = 1_500_000
    # Max prior session images attached to a vision turn for follow-up questions
    # ("а переведи вон ту надпись на ней" referring to an earlier photo).
    vision_session_images: int = 2
    # Hard cap on images sent to the model in one turn (current + session).
    vision_max_images_per_turn: int = 2
    # Text stored for a caption-less photo so the API schema (min_length=1), the
    # DB row and the session history stay consistent; the vision path ignores it.
    vision_photo_placeholder: str = "[фото]"
    # Reply to ANY photo ("auto-answer every image") — the pre-change behavior.
    # When False (default), Vanessa replies to a bare caption-less photo only
    # when she is actively listening (recently talked with her) or the photo is
    # addressed to her (reply to her message / a mention); otherwise the image
    # is not even analyzed. Captioned photos always flow through the normal gate.
    vision_reply_to_any_photo: bool = False
    # Media-group (album) aggregation: Telegram delivers each album photo as a
    # SEPARATE message sharing the same ``media_group_id``. To let Vanessa see
    # the whole album at once (e.g. compare two paintings), the bot buffers the
    # group and flushes ONE turn with all photos after the group has been quiet
    # for this many seconds (restarted on every photo of the group).
    vision_media_group_debounce_seconds: float = 1.5
    # Safety cap on how many photos are merged into a single media-group turn.
    vision_media_group_max_photos: int = 10
    # Photo album: max photos listed in the compose prompt that the bot could
    # re-send (selected by RAG "по смыслу" + recent session).
    vision_photo_candidates: int = 5
    # Background enrichment: after a photo turn, generate a short description
    # with the vision model and store it (photo_caption) so bare photos become
    # findable "by meaning" in RAG.
    vision_photo_caption_enabled: bool = True
    # Caption model; empty = the active vision model (deepseek_vision_model).
    vision_photo_caption_model: str = ""
    # Max length of the generated photo caption.
    vision_photo_caption_max_chars: int = 160

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
    # Defer undecided questions (no deterministic address/trigger/window) to the
    # reaction gate instead of hard-dropping them as side_talk: the bot then
    # actually "considers" contextually-addressed questions in an active
    # conversation. Trade-off: those questions reach the planner even when they
    # end up ignored, so a busy group pays more planner/LLM calls.
    decision_prefilter_defer_questions: bool = True
    decision_post_reply_listen_count: int = 4
    decision_session_idle_seconds: int = 300
    # Compose-stage refusal: when the answer-preparation (compose) stage detects
    # a repeated same-sender message, or the compose model returns an empty
    # "stay silent" reply, the turn is refused (finalized as IGNORE) instead of
    # sending an empty/duplicate answer. A final safety net for spam the earlier
    # gate let through (also covers the vision forced-turn path that bypasses
    # the decision engine).
    decision_compose_refuse_enabled: bool = True

    # Lightweight Decision Gate (reaction classifier) — runs BEFORE the heavy
    # LLM turn planner. One fast, cheap YES/NO call decides whether the message
    # needs a bot reaction at all; NO finalizes the turn instantly (the bot
    # stays silent), saving the planner/RAG/compose chain on empty or
    # non-reply-worthy group-chat messages. Fail-open: errors/ambiguous replies
    # always let the turn proceed.
    decision_reaction_gate_enabled: bool = True
    # Empty = the active planner model (deepseek-chat, a fast non-reasoning
    # model) — perfect for a tiny binary classification with max_tokens=5.
    decision_reaction_gate_model: str = ""
    decision_reaction_gate_max_tokens: int = 5
    # How many recent messages (at most) are rendered as context for the gate.
    decision_reaction_gate_recent_window: int = 4
    # Tier-1 zero-cost deterministic short-circuit (question/trigger/modal/
    # imperative verb, direct address, noise). When on, clear requests are
    # resolved WITHOUT any LLM call, so the gate adds zero latency on the happy
    # path; only genuinely ambiguous messages hit the cheap LLM tier.
    decision_reaction_gate_heuristics_enabled: bool = True
    # High-confidence bypasses: a direct reply to the bot's message and a
    # post-reply listen window are never classified — the bot is expected to
    # answer there, so we never risk dropping the turn.
    decision_reaction_gate_bypass_reply_to_bot: bool = True
    decision_reaction_gate_bypass_listen_window: bool = True
    # Sender-aware continuation follow-ups: a short demand right after the
    # bot's own reply from the same user ("а ещё" = "tell me another one") is
    # an explicit request even when the post-reply listen window has expired.
    # Applies to both the planner prefilter and the reaction-gate Tier-1.
    decision_continuation_follow_up_enabled: bool = True

    # Directory with one YAML file per section (bot, persona, llm, ...)
    # or a single monolithic YAML file for backward compatibility.
    content_config_path: str = "config/content"
    nicknames_config_path: str = "config/nicknames.yaml"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://api:8000"
    api_internal_token: str = ""
    api_auto_create_schema: bool = False
    # HTTP timeouts for the bot -> API /api/v1/chat call. The full pipeline
    # (Gate -> Retrieve -> Compose -> Critique) can take 2-6s+, so the read
    # timeout must sit comfortably above that. The connect timeout stays short
    # so a dead API is reported quickly instead of hanging the handler.
    api_client_read_timeout: float = 120.0
    api_client_connect_timeout: float = 10.0

    # How often the bot re-sends the "typing..." chat action while the API
    # pipeline runs. Telegram expires the typing state after ~5s, so keep this
    # comfortably below that (4s default).
    bot_typing_interval_seconds: float = 4.0
    # Delay (seconds) between consecutive blocks of a multi-message reply, so
    # the messages appear one by one ("по мере написания"). 0 = back-to-back.
    bot_message_delay_seconds: float = 0.7
    # Safety cap on how many reply blocks are sent in one turn; anything beyond
    # is dropped so a runaway model can never flood the chat.
    bot_max_messages: int = 8

    indexing_max_retries: int = 2
    llm_max_retries: int = 2

    # Bounded background executor for non-critical post-reply work (memory
    # extraction, metrics snapshots, message indexing). The queue is bounded so
    # overload drops jobs (fail-open) instead of blocking the reply path.
    background_queue_size: int = 200
    background_workers: int = 2

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

    # --- Observability: Prometheus metrics -----------------------------------
    # Expose vanessa_* metrics via GET /metrics (API) and a threaded HTTP
    # endpoint on the bot (BOT_METRICS_PORT). Metrics are cheap and safe to keep
    # on; they power the Grafana dashboards and the in-process AlertManager.
    metrics_enabled: bool = True
    # Require X-Internal-Token on GET /metrics. Prometheus itself can be given
    # the header via scrape_configs.bearer_token; disabled by default so a
    # fresh Prometheus scrape works out of the box.
    metrics_require_token: bool = False
    # Port for the bot process Prometheus HTTP endpoint (scraped by Prometheus).
    bot_metrics_port: int = 9101

    # --- Observability: LLM cost estimation -----------------------------------
    # USD per 1M tokens used as a fallback when a provider/model has no known
    # price in the built-in table (app.observability.metrics._LLM_PRICING_PER_1M).
    # Defaults match DeepSeek-chat (input / output). The cost metric is an
    # estimate for spend monitoring, not a billing ledger.
    llm_default_prompt_cost_per_1m: float = 0.27
    llm_default_completion_cost_per_1m: float = 1.10
    # USD per 1M cache-hit input tokens (DeepSeek KV-cache billing). Prompt
    # tokens served from the KV-cache cost a fraction of a full re-encode, so
    # the estimate splits input tokens into cache-hit (this price) and
    # cache-miss (llm_default_prompt_cost_per_1m). Set to the prompt price to
    # ignore the discount.
    llm_default_cache_hit_prompt_cost_per_1m: float = 0.07

    # --- Observability: Langfuse LLM/RAG tracing -------------------------------
    # Off by default; the pipeline falls back to a NullTracer (no network).
    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    # 0..1 — fraction of turns that are traced (1.0 = trace everything).
    langfuse_sample_rate: float = 1.0
    # Salt for hashing user/chat ids before they leave the process (privacy).
    langfuse_id_salt: str = "vanessa"
    # Flush interval (seconds) for the Langfuse client.
    langfuse_flush_interval: int = 30

    # --- Observability: RAG Triad evaluation ----------------------------------
    # Deterministic RAG signals (score histograms, empty-retrieval counter) are
    # always collected. This flag enables the sampled LLM-as-judge evaluations
    # (context relevance / groundedness / answer relevance), which cost tokens.
    rag_eval_enabled: bool = False
    # 0..1 — fraction of replied turns that get an LLM-as-judge evaluation.
    rag_eval_sample_rate: float = 0.05
    # Judge model; empty = the active planner model.
    rag_eval_model: str = ""

    # --- Observability: Alerting (Telegram dev channel) -----------------------
    # Periodic in-process evaluation of local metric windows with alerts sent
    # to ALERTING_DEV_CHAT_ID via the bot token.
    alerting_enabled: bool = False
    alerting_check_interval_seconds: int = 60
    alerting_cooldown_seconds: int = 600
    alerting_window_seconds: int = 300
    # Alert when the share of errored turns/LLM calls over the window exceeds this.
    alerting_error_rate_threshold: float = 0.05
    # Alert when turn latency p95 over the window exceeds this (seconds).
    alerting_latency_p95_threshold: float = 7.0
    # Alert when the share of empty RAG retrievals over the window exceeds this.
    alerting_rag_empty_threshold: float = 0.5
    # Alert when the share of empty/blank LLM completions over the window exceeds
    # this (among successful calls).
    alerting_llm_empty_threshold: float = 0.1
    # Alert when estimated LLM spend over the window exceeds this (USD) — catches
    # runaway loops and spam bursts.
    alerting_cost_window_threshold_usd: float = 5.0
    # Private Telegram chat/channel that receives alerts (bot must be a member).
    alerting_dev_chat_id: int = 0
    # How often (hours) to probe the LLM provider balance; 0 disables the check.
    alerting_balance_check_hours: int = 24

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
    # Multi-person retrieval: when several people are mentioned ("крабер и
    # личь"), fetch up to this many dossiers (each still bounded by
    # knowledge_people_raw_max_chars / portraits).
    knowledge_people_max_blocks: int = 3
    knowledge_model: str = ""
    knowledge_memory_enabled: bool = True
    knowledge_memory_cooldown_seconds: int = 300
    knowledge_memory_max_tokens: int = 512
    # Deterministic prefilter: skip the memory LLM call when the new transcript
    # is mundane (short replies, chit-chat) and would only return an empty plan.
    knowledge_memory_prefilter_enabled: bool = True
    knowledge_memory_prefilter_min_messages: int = 1
    knowledge_memory_prefilter_min_content_chars: int = 40
    knowledge_memory_prefilter_score_threshold: float = 1.5
    knowledge_sweep_enabled: bool = True
    knowledge_sweep_interval_messages: int = 50
    knowledge_sweep_batch_size: int = 200
    knowledge_sweep_window_size: int = 40
    knowledge_sweep_window_overlap: int = 10
    knowledge_sweep_poll_seconds: int = 60

    # Semantic vector search over the knowledge vault (Qdrant "knowledge").
    knowledge_vector_top_k: int = 10
    knowledge_vector_min_score: float = 0.3

    # Participants digest injected into the query-composition prompt. Instead of
    # dumping ALL people into every planner call, only those mentioned in the
    # current message + the recent window are rendered (dynamic, bounded); when
    # nothing is mentioned, a small fallback floor keeps disambiguation anchors.
    knowledge_participant_max_people: int = 10
    knowledge_participant_max_facts: int = 3
    # How many recent messages are scanned for participant mentions.
    knowledge_participant_recent_window: int = 5
    # Fallback floor of people in the digest when nothing is mentioned.
    knowledge_participant_min_people: int = 3

    # Mood & relationship metrics (knowledge vault).
    knowledge_metrics_enabled: bool = True
    knowledge_metrics_model: str = ""
    knowledge_metrics_max_tokens: int = 768
    knowledge_metrics_cooldown_seconds: int = 900
    knowledge_metrics_history_days: int = 14

    # Hierarchical dossiers: compact LLM portraits per participant. A background
    # worker compresses each People card into a 3-5 sentence portrait stored in
    # the card's frontmatter; the compose prompt injects only the relevant
    # person's portrait (not the full 100+ line dossier) unless a concrete fact
    # is asked (then the raw dossier is pulled, bounded by
    # knowledge_people_raw_max_chars).
    knowledge_portrait_enabled: bool = True
    knowledge_portrait_model: str = ""
    knowledge_portrait_max_tokens: int = 384
    knowledge_portrait_poll_seconds: int = 300
    knowledge_portrait_max_chars: int = 4000
    # Raw dossier facts injected into the compose prompt on a concrete-fact
    # question about a person ("во что играет Крабер?").
    knowledge_people_raw_max_chars: int = 1400
    # Detailed person retrieval: when a question asks to reveal a person in
    # depth (knowledge_detail=true), instead of injecting a single portrait or a
    # bounded raw dump, the dossier is split into text blocks (chunks), each
    # embedded separately, and the top matching blocks are injected. A short
    # portrait is only enough for passing mentions — this option powers the
    # "tell me in detail about X" case.
    knowledge_people_chunks_enabled: bool = True
    # Target size of a dossier block (chars) when chunking People notes.
    knowledge_people_chunk_chars: int = 600
    # Overlap between neighbouring chunks (chars) so a fact spanning a boundary
    # stays readable.
    knowledge_people_chunk_overlap: int = 120
    # How many of the strongest matching blocks from a person's dossier are
    # injected on a detail query (semantic rank order).
    knowledge_people_detail_blocks: int = 5

    # Compose-prompt budget: per-section and global char caps applied in
    # PromptBuilder so a bloated context never blows the LLM window. Caps live
    # in config/content/llm.yaml (budget: section); this flag gates the guard.
    compose_budget_enabled: bool = True

    # Behavioral feedback from metrics.
    decision_metrics_rule_enabled: bool = True
    decision_toxicity_ignore_threshold: float = 0.8
    decision_trust_ignore_threshold: float = 30.0
    feedback_tone_enabled: bool = True
    # Loop-repetition attitude mechanic: a sender re-asking the SAME topic in a
    # loop (different phrasings, same meaning) raises Vanessa's runtime
    # annoyance (see app/decision/repeated_loop.py). At high annoyance her
    # ignore tendency becomes maximal — weak/non-essential messages are skipped
    # (LowAttitudeRule) — and replies turn cold (compose annoyance note).
    decision_low_attitude_rule_enabled: bool = True
    decision_annoyance_ignore_threshold: float = 0.6
    decision_low_attitude_trust_threshold: float = 25.0
    decision_low_attitude_sympathy_threshold: float = -0.3
    decision_loop_window: int = 10
    decision_loop_similarity_threshold: float = 0.4
    decision_loop_decay_half_life_seconds: int = 3600
    feedback_annoyance_threshold: float = 0.5

    # --- Web search (the "googling" skill) ------------------------------------
    # Master switch for live internet search. When on, the gate planner may flag
    # a turn with web_search=true and the Retrieve stage runs a real search API;
    # the results are injected into the compose prompt as a "live web results"
    # block (search-then-inject, no tool-calling loop, so no extra LLM round-trip).
    web_search_enabled: bool = False
    # Search provider: "tavily" (default, built for LLM agents), "serper",
    # or "duckduckgo" (free but rate-limited / less stable).
    web_search_provider: str = "tavily"
    web_search_api_key: str = ""
    # Max results injected into the compose prompt per turn.
    web_search_max_results: int = 5
    # Hard cap on the search HTTP call so a slow provider never stalls the reply.
    web_search_timeout_seconds: float = 5.0
    # Per-result snippet cap (chars); longer snippets are cut at a boundary.
    # The whole web-results block is capped by the compose prompt budget
    # (config/content/llm.yaml budget: web_blocks), so it trims together with
    # the rest of the context.
    web_search_snippet_max_chars: int = 300

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

# huggingface_hub (used by sentence-transformers to download
# EMBEDDING_MODEL_NAME) reads the token from os.environ, not from pydantic
# settings. Propagate the .env HF_TOKEN into the process environment so local
# (non-Docker) runs are authenticated too; a real environment variable always
# wins over the .env value.
if settings.hf_token:
    os.environ.setdefault("HF_TOKEN", settings.hf_token)
