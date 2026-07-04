from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    session_window_size: int
    session_idle_seconds: float
    post_reply_listen_count: int
    planner_prefilter_enabled: bool
    defer_index_on_ignore: bool = True
    humor_top_k: int = 15
    humor_anchor_max: int = 5
    humor_window_before: int = 8
    humor_window_after: int = 4
    humor_max_quotes: int = 3
    humor_min_quote_score: float = 2.5

    @classmethod
    def from_settings(cls) -> "OrchestratorConfig":
        return cls(
            session_window_size=settings.decision_session_window_size,
            session_idle_seconds=float(settings.decision_session_idle_seconds),
            post_reply_listen_count=settings.decision_post_reply_listen_count,
            planner_prefilter_enabled=settings.decision_planner_prefilter,
            humor_top_k=settings.rag_humor_top_k,
            humor_anchor_max=settings.rag_humor_anchor_max,
            humor_window_before=settings.rag_humor_window_before,
            humor_window_after=settings.rag_humor_window_after,
            humor_max_quotes=settings.rag_humor_max_quotes,
            humor_min_quote_score=settings.rag_humor_min_quote_score,
        )
