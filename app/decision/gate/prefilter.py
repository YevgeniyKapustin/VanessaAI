from dataclasses import dataclass

from app.core.messages import ContextMessage
from app.core.session.chat_session_state import in_post_reply_listen_window
from app.decision.gate.reply_eligibility import ReplyEligibility

__all__ = [
    "PlannerPrefilter",
    "PlannerPrefilterResult",
    "in_post_reply_listen_window",
    "user_messages_since_last_bot",
]


@dataclass(frozen=True, slots=True)
class PlannerPrefilterResult:
    run_planner: bool
    reason: str = ""


def user_messages_since_last_bot(recent_messages: list[ContextMessage]) -> int:
    count = 0
    for message in reversed(recent_messages):
        if message.role == "assistant":
            break
        if message.role == "user":
            count += 1
    return count


class PlannerPrefilter:
    def __init__(self, eligibility: ReplyEligibility) -> None:
        self._eligibility = eligibility

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
    ) -> PlannerPrefilterResult:
        verdict = self._eligibility.evaluate_prefilter(
            text,
            recent_messages,
            telegram_chat_id=telegram_chat_id,
            sender_telegram_id=sender_telegram_id,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
        )
        return PlannerPrefilterResult(verdict.run_planner, verdict.reason)
