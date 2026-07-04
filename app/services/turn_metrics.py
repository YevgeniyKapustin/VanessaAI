from collections import Counter
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class TurnMetricsSnapshot:
    total: int = 0
    replies: int = 0
    ignores: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    by_action_reason: dict[str, int] = field(default_factory=dict)
    planner_skipped: int = 0
    deep_search_used: int = 0


class TurnMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._total = 0
        self._replies = 0
        self._ignores = 0
        self._planner_skipped = 0
        self._deep_search_used = 0
        self._by_reason: Counter[str] = Counter()
        self._by_action_reason: Counter[str] = Counter()

    def record_turn(
        self,
        *,
        action: str,
        reason: str,
        planner_skipped: bool = False,
        deep_search: bool = False,
    ) -> None:
        with self._lock:
            self._total += 1
            if action == "reply":
                self._replies += 1
            else:
                self._ignores += 1
            if planner_skipped:
                self._planner_skipped += 1
            if deep_search:
                self._deep_search_used += 1
            self._by_reason[reason] += 1
            self._by_action_reason[f"{action}:{reason}"] += 1

    def snapshot(self) -> TurnMetricsSnapshot:
        with self._lock:
            return TurnMetricsSnapshot(
                total=self._total,
                replies=self._replies,
                ignores=self._ignores,
                by_reason=dict(self._by_reason),
                by_action_reason=dict(self._by_action_reason),
                planner_skipped=self._planner_skipped,
                deep_search_used=self._deep_search_used,
            )

    def reset(self) -> None:
        with self._lock:
            self._total = 0
            self._replies = 0
            self._ignores = 0
            self._planner_skipped = 0
            self._deep_search_used = 0
            self._by_reason.clear()
            self._by_action_reason.clear()


turn_metrics = TurnMetrics()
