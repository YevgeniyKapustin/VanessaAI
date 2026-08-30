from dataclasses import dataclass, field


@dataclass
class TurnMetricsSnapshot:
    total: int = 0
    replies: int = 0
    ignores: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    by_action_reason: dict[str, int] = field(default_factory=dict)
    planner_skipped: int = 0
    deep_search_used: int = 0
