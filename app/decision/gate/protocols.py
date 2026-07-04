from typing import Protocol

from app.core.messages import ContextMessage
from app.decision.gate.prefilter import PlannerPrefilterResult
from app.llm.planner.turn_planner import TurnPlan


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
