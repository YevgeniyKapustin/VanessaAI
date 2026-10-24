from typing import Protocol

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.gate.eligibility.prefilter import PlannerPrefilterResult
from vanessa.pipeline.decision.gate.eligibility.reply_eligibility import (
    HardIgnoreResult,
    PrefilterVerdict,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate import ReactionGateResult
from vanessa.pipeline.decision.turn_plan import TurnPlan


class ReplyEligibilityProtocol(Protocol):
    def hard_ignore(self, context: DecisionContext) -> HardIgnoreResult | None: ...

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
        addressing: str = "telegram",
        force_listen_window: bool = False,
    ) -> PrefilterVerdict: ...

    def should_block_compose(
        self,
        context: DecisionContext,
        *,
        humor_ok: bool = False,
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
        addressing: str = "telegram",
        force_listen_window: bool = False,
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
        sender_name: str = "",
        sender_is_owner: bool = False,
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
