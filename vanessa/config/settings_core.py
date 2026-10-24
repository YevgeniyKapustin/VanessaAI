"""Agent-core settings mixin: LLM, planner, decision, vision, tools."""

from __future__ import annotations


class CoreMixin:
    """Agent-core (orchestrator) settings: LLM, planner, decision, vision, tools."""

    # --- LLM providers -------------------------------------------------------
    llm_provider: str = "deepseek"  # "deepseek" (default) or "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_planner_model: str = ""
    anthropic_max_tokens: int = 4096

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_planner_model: str = "deepseek-chat"
    deepseek_max_tokens: int = 4096

    # --- Vision (DeepSeek multimodal) ----------------------------------------
    vision_enabled: bool = True
    deepseek_vision_model: str = "deepseek-flash"
    vision_max_image_bytes: int = 1_500_000
    vision_session_images: int = 2
    vision_max_images_per_turn: int = 2
    vision_reply_to_any_photo: bool = False
    vision_media_group_debounce_seconds: float = 1.5
    vision_media_group_max_photos: int = 10
    vision_photo_candidates: int = 5
    vision_photo_caption_enabled: bool = True
    vision_photo_caption_model: str = ""
    vision_photo_caption_max_chars: int = 160

    # --- Turn planner ---------------------------------------------------------
    rag_query_rewrite_use_llm: bool = True

    # --- Decision engine ------------------------------------------------------
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
    knowledge_model: str = ""
    knowledge_participant_max_people: int = 10
    knowledge_participant_max_facts: int = 3
    knowledge_participant_recent_window: int = 5
    knowledge_participant_min_people: int = 3
    compose_budget_enabled: bool = True
    # filesystem (default, tests/local) or postgres (production vault).
    knowledge_store: str = "filesystem"

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
