from typing import Protocol

from app.core.messages import ContextMessage
from app.decision.detectors.intent import IntentResult
from app.decision.gate.prefilter import PlannerPrefilterResult
from app.decision.gate.reply_eligibility import HardIgnoreResult, PrefilterVerdict
from app.llm.planner.turn_planner import TurnPlan


class ReplyEligibilityProtocol(Protocol):
    def hard_ignore(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        telegram_chat_id: int = 0,
        sender_telegram_id: int = 0,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        intent: IntentResult | None = None,
    ) -> HardIgnoreResult | None: ...

    def evaluate_prefilter(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        telegram_chat_id: int = 0,
        sender_telegram_id: int = 0,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
    ) -> PrefilterVerdict: ...

    def should_block_compose(
        self,
        text: str,
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        should_reply: bool | None = None,
        in_listen_window: bool = False,
        humor_ok: bool = False,
        trigger_detected: bool = False,
        intent: IntentResult | None = None,
    ) -> bool: ...


class PlannerPrefilterProtocol(Protocol):
    def evaluate(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        telegram_chat_id: int = 0,
        sender_telegram_id: int = 0,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
    ) -> PlannerPrefilterResult: ...


class TurnPlannerProtocol(Protocol):
    async def prepare(
        self,
        message: str,
        recent_messages: list[ContextMessage] | None = None,
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
    ) -> TurnPlan: ...

