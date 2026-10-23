from dataclasses import dataclass

from vanessa.config import settings
from vanessa.config.conversation_config import load_conversation_config


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    session_window_size: int
    session_idle_seconds: float
    post_reply_listen_count: int
    planner_prefilter_enabled: bool
    # Compose-stage refusal: refuse the answer (finalize as IGNORE) when the
    # answer-preparation stage detects a repeated same-sender message or the
    # compose model returns an empty "stay silent" reply.
    compose_refuse_enabled: bool = True

    @classmethod
    def from_settings(cls) -> "OrchestratorConfig":
        conversation = load_conversation_config()
        return cls(
            session_window_size=conversation.session_window_size,
            session_idle_seconds=conversation.session_idle_seconds,
            post_reply_listen_count=conversation.post_reply_listen_count,
            planner_prefilter_enabled=settings.decision_planner_prefilter,
            compose_refuse_enabled=settings.decision_compose_refuse_enabled,
        )
