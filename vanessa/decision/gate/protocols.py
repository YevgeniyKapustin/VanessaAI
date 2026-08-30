from typing import Protocol

from vanessa.core.messages import ContextMessage
from vanessa.decision.detectors.intent import IntentResult
from vanessa.decision.gate.prefilter import PlannerPrefilterResult
from vanessa.decision.gate.reaction_gate import ReactionGateResult
from vanessa.decision.gate.reply_eligibility import HardIgnoreResult, PrefilterVerdict
from vanessa.llm.planner.turn_planner import TurnPlan


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
        recent_messages: list[ContextMessage] | None = None,
        sender_telegram_id: int = 0,
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


class ReactionGateProtocol(Protocol):
    """Lightweight pre-planner classifier: should the bot react at all?

    Runs BEFORE the expensive LLM turn planner. ``respond=False`` means the
    pipeline finalizes immediately (the bot stays silent); ``respond=True``
    lets the turn proceed to the planner.
    """

    async def evaluate(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
        sender_telegram_id: int | None = None,
    ) -> ReactionGateResult: ...

