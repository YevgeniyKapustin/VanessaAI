from dataclasses import dataclass

from app.core.messages import ContextMessage
from app.decision.intent import IntentDetector
from app.decision.noise import NoiseFilter
from app.decision.reply_expectation import is_conversation_closure
from app.decision.triggers import TriggerKeywordChecker


@dataclass(frozen=True, slots=True)
class PlannerPrefilterResult:
    run_planner: bool
    reason: str = ""


def _follows_bot(recent_messages: list[ContextMessage]) -> bool:
    if len(recent_messages) < 2:
        return False
    return recent_messages[-2].role == "assistant"


def user_messages_since_last_bot(recent_messages: list[ContextMessage]) -> int:
    count = 0
    for message in reversed(recent_messages):
        if message.role == "assistant":
            break
        if message.role == "user":
            count += 1
    return count


def in_post_reply_listen_window(
    recent_messages: list[ContextMessage],
    *,
    max_messages: int,
) -> bool:
    if max_messages <= 0 or not recent_messages:
        return False
    user_count = 0
    for message in reversed(recent_messages):
        if message.role == "assistant":
            return 0 < user_count <= max_messages
        if message.role == "user":
            user_count += 1
    return False


class PlannerPrefilter:
    def __init__(
        self,
        intent_detector: IntentDetector,
        trigger_checker: TriggerKeywordChecker,
        noise_filter: NoiseFilter,
        *,
        post_reply_listen_count: int = 5,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._noise = noise_filter
        self._post_reply_listen_count = post_reply_listen_count

    def evaluate(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
    ) -> PlannerPrefilterResult:
        directly_addressed = mentions_bot or reply_to_bot
        intent = self._intent.detect(text)
        trigger = self._triggers.detect(text)
        follows_bot = _follows_bot(recent_messages)
        in_listen_window = in_post_reply_listen_window(
            recent_messages,
            max_messages=self._post_reply_listen_count,
        )

        if directly_addressed:
            return PlannerPrefilterResult(True, "direct_address")

        if intent.mentions_bot:
            return PlannerPrefilterResult(True, "bot_name")

        if in_listen_window:
            if self._noise.is_noise(text) and not trigger.detected:
                return PlannerPrefilterResult(False, "noise")
            if is_conversation_closure(text):
                return PlannerPrefilterResult(False, "closure")
            return PlannerPrefilterResult(True, "listen_window")

        if self._noise.is_noise(text) and not trigger.detected:
            return PlannerPrefilterResult(False, "noise")

        if is_conversation_closure(text):
            return PlannerPrefilterResult(False, "closure")

        if follows_bot and not self._noise.is_noise(text):
            if directly_addressed or intent.mentions_bot or trigger.detected:
                return PlannerPrefilterResult(True, "follow_up")
            if intent.has_question:
                return PlannerPrefilterResult(True, "follow_up_question")

        if trigger.detected and (
            directly_addressed or intent.mentions_bot or follows_bot
        ):
            return PlannerPrefilterResult(True, "trigger")

        return PlannerPrefilterResult(False, "side_talk")
