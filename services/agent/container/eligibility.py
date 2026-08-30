from __future__ import annotations

from services.agent.container.signals import MentionSignals
from vanessa.config.content import get_content
from vanessa.config.conversation_config import load_conversation_config
from vanessa.pipeline.decision import SessionWindowAnalyzer
from vanessa.pipeline.decision.gate.prefilter import PlannerPrefilter
from vanessa.pipeline.decision.gate.reply_eligibility import ReplyEligibility
from vanessa.pipeline.decision.gate.user_ignore import ChatIgnoreRegistry


class EligibilityGates:
    def __init__(
        self,
        signals: MentionSignals,
        ignore_registry: ChatIgnoreRegistry,
    ) -> None:
        conversation = load_conversation_config()
        self.reply = ReplyEligibility(
            signals.intent,
            signals.triggers,
            signals.noise,
            ignore_registry,
            post_reply_listen_count=conversation.post_reply_listen_count,
            post_reply_listen_idle_seconds=conversation.session_idle_seconds,
        )
        self.prefilter = PlannerPrefilter(self.reply)
        self.session = SessionWindowAnalyzer(
            window_size=conversation.session_window_size,
            intent_detector=signals.intent,
            trigger_checker=signals.triggers,
        )
        self.block_consecutive_replies = (
            get_content().decision.block_consecutive_replies
        )
