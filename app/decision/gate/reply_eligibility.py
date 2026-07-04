from __future__ import annotations

from dataclasses import dataclass

from app.core.messages import ContextMessage
from app.core.session.chat_session_state import in_post_reply_listen_window
from app.decision.detectors.intent import IntentDetector, IntentResult
from app.decision.detectors.noise import NoiseFilter
from app.decision.detectors.triggers import TriggerKeywordChecker
from app.decision.gate.addressing import is_addressed_to_bot
from app.decision.gate.quote_echo import is_recursive_quote_loop
from app.decision.gate.reply_expectation import (
    is_conversation_closure,
    is_dismissal_request,
    is_third_party_about_bot,
    is_unsolicited_remark,
)
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.models import DecisionReason


@dataclass(frozen=True, slots=True)
class HardIgnoreResult:
    tag: str
    decision_reason: DecisionReason


@dataclass(frozen=True, slots=True)
class PrefilterVerdict:
    run_planner: bool
    reason: str = ""


def prefilter_tag_to_decision_reason(tag: str) -> DecisionReason:
    mapping = {
        "ignored_user": DecisionReason.USER_IGNORED,
        "dismissal": DecisionReason.DISMISSAL,
        "quote_echo": DecisionReason.QUOTE_ECHO,
        "side_talk": DecisionReason.PREFILTER,
        "noise": DecisionReason.PREFILTER,
        "closure": DecisionReason.PREFILTER,
    }
    return mapping.get(tag, DecisionReason.PREFILTER)


def _follows_bot(recent_messages: list[ContextMessage]) -> bool:
    if len(recent_messages) < 2:
        return False
    return recent_messages[-2].role == "assistant"


class ReplyEligibility:
    def __init__(
        self,
        intent_detector: IntentDetector,
        trigger_checker: TriggerKeywordChecker,
        noise_filter: NoiseFilter,
        ignore_registry: ChatIgnoreRegistry,
        *,
        post_reply_listen_count: int = 2,
        post_reply_listen_idle_seconds: float = 0,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._noise = noise_filter
        self._ignore_registry = ignore_registry
        self._post_reply_listen_count = post_reply_listen_count
        self._post_reply_listen_idle_seconds = post_reply_listen_idle_seconds

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
    ) -> HardIgnoreResult | None:
        detected = intent if intent is not None else self._intent.detect(text)
        directly_addressed = mentions_bot or reply_to_bot

        if (
            telegram_chat_id
            and sender_telegram_id
            and self._ignore_registry.is_ignored(
                telegram_chat_id,
                sender_telegram_id,
            )
        ):
            return HardIgnoreResult("ignored_user", DecisionReason.USER_IGNORED)

        if is_dismissal_request(text):
            return HardIgnoreResult("dismissal", DecisionReason.DISMISSAL)

        if is_recursive_quote_loop(
            text,
            recent_messages,
            reply_to_bot=reply_to_bot,
        ):
            return HardIgnoreResult("quote_echo", DecisionReason.QUOTE_ECHO)

        if is_third_party_about_bot(text) and not directly_addressed:
            return HardIgnoreResult("side_talk", DecisionReason.NOT_EXPECTED)

        if (
            reply_to_other_user
            and not directly_addressed
            and not detected.mentions_bot
        ):
            return HardIgnoreResult("side_talk", DecisionReason.NOT_EXPECTED)

        return None

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
    ) -> PrefilterVerdict:
        intent = self._intent.detect(text)
        hard = self.hard_ignore(
            text,
            recent_messages,
            telegram_chat_id=telegram_chat_id,
            sender_telegram_id=sender_telegram_id,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            intent=intent,
        )
        if hard is not None:
            return PrefilterVerdict(False, hard.tag)

        directly_addressed = mentions_bot or reply_to_bot
        trigger = self._triggers.detect(text)
        follows_bot = _follows_bot(recent_messages)

        in_listen_window = in_post_reply_listen_window(
            recent_messages,
            max_messages=self._post_reply_listen_count,
            max_idle_seconds=self._post_reply_listen_idle_seconds,
        )

        if directly_addressed:
            return PrefilterVerdict(True, "direct_address")

        if intent.mentions_bot:
            return PrefilterVerdict(True, "bot_name")

        if in_listen_window:
            if self._noise.is_noise(text) and not trigger.detected:
                return PrefilterVerdict(False, "noise")
            if is_unsolicited_remark(text):
                return PrefilterVerdict(False, "side_talk")
            if is_conversation_closure(text):
                return PrefilterVerdict(False, "closure")
            return PrefilterVerdict(True, "listen_window")

        if self._noise.is_noise(text) and not trigger.detected:
            return PrefilterVerdict(False, "noise")

        if is_conversation_closure(text):
            return PrefilterVerdict(False, "closure")

        if follows_bot and not self._noise.is_noise(text):
            if directly_addressed or intent.mentions_bot or trigger.detected:
                return PrefilterVerdict(True, "follow_up")
            if intent.has_question:
                return PrefilterVerdict(True, "follow_up_question")

        if trigger.detected and (
            directly_addressed or intent.mentions_bot or follows_bot
        ):
            return PrefilterVerdict(True, "trigger")

        return PrefilterVerdict(False, "side_talk")

    def allows_compose(
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
    ) -> bool:
        if humor_ok:
            return True
        return is_addressed_to_bot(
            text,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            should_reply=should_reply,
            in_listen_window=in_listen_window,
            trigger_detected=trigger_detected,
            intent=intent,
        )

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
    ) -> bool:
        if humor_ok:
            return False
        if (
            reply_to_other_user
            and not mentions_bot
            and not reply_to_bot
        ):
            return True
        if should_reply is False:
            return True
        if in_listen_window:
            return False
        return not self.allows_compose(
            text,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            should_reply=should_reply,
            in_listen_window=in_listen_window,
            trigger_detected=trigger_detected,
            intent=intent,
        )
