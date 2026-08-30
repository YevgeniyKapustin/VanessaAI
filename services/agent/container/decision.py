from __future__ import annotations

from services.agent.container.eligibility import EligibilityGates
from services.agent.container.signals import MentionSignals
from vanessa.config.content import get_content
from vanessa.config.settings import settings
from vanessa.llm.completers import create_chat_completer
from vanessa.pipeline.decision import RateLimiter
from vanessa.pipeline.decision.gate.reaction_gate import ReactionGate
from vanessa.pipeline.decision.gate.user_ignore import ChatIgnoreRegistry


class DecisionStack:
    def __init__(
        self,
        signals: MentionSignals | None = None,
        ignore_registry: ChatIgnoreRegistry | None = None,
        rate_limiter: RateLimiter | None = None,
        eligibility: EligibilityGates | None = None,
        reaction_gate: ReactionGate | None = None,
    ) -> None:
        self.signals = signals or MentionSignals()
        self.ignore_registry = ignore_registry or ChatIgnoreRegistry()
        self.rate_limiter = rate_limiter or RateLimiter(
            max_replies=settings.decision_rate_limit_per_minute,
            window_seconds=60,
        )
        self.eligibility = eligibility or EligibilityGates(
            self.signals,
            self.ignore_registry,
        )
        self.reaction_gate = reaction_gate or ReactionGate(
            get_content(),
            llm_client=create_chat_completer(),
        )
