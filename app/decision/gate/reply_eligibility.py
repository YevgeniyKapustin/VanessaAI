from __future__ import annotations

from dataclasses import dataclass

from app.config.content import get_continuation_phrases
from app.config.settings import settings
from app.core.messages import ContextMessage
from app.core.session.chat_session_state import in_post_reply_listen_window
from app.decision.detectors.intent import IntentDetector, IntentResult
from app.decision.detectors.noise import NoiseFilter
from app.decision.detectors.triggers import TriggerKeywordChecker
from app.decision.gate.addressing import is_addressed_to_bot
from app.decision.gate.continuation import is_sender_continuation_demand
from app.decision.gate.quote_echo import is_recursive_quote_loop
from app.decision.gate.reply_expectation import (
    is_conversation_closure,
    is_dismissal_request,
    is_third_party_about_bot,
    is_unsolicited_remark,
    mention_warrants_reply,
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


def _thread_dismissed(recent_messages: list[ContextMessage]) -> bool:
    """Whether the user dismissed the bot after the last assistant message.

    A dismissal ("хватит", "заткнись", ...) closes the thread: even a later
    question should not be deferred to the reaction gate.
    """
    for message in reversed(recent_messages):
        if message.role == "assistant":
            return False
        if message.role == "user" and is_dismissal_request(message.content):
            return True
    return False


class ReplyEligibility:
    def __init__(
        self,
        intent_detector: IntentDetector,
        trigger_checker: TriggerKeywordChecker,
        noise_filter: NoiseFilter,
        ignore_registry: ChatIgnoreRegistry,
        *,
        post_reply_listen_count: int = 4,
        post_reply_listen_idle_seconds: float = 0,
        continuation_follow_up_enabled: bool | None = None,
        continuation_phrases: tuple[str, ...] | None = None,
        defer_questions: bool | None = None,
    ) -> None:
        self._intent = intent_detector
        self._triggers = trigger_checker
        self._noise = noise_filter
        self._ignore_registry = ignore_registry
        self._post_reply_listen_count = post_reply_listen_count
        self._post_reply_listen_idle_seconds = post_reply_listen_idle_seconds
        self._defer_questions = (
            settings.decision_prefilter_defer_questions
            if defer_questions is None
            else defer_questions
        )
        self._continuation_enabled = (
            settings.decision_continuation_follow_up_enabled
            if continuation_follow_up_enabled is None
            else continuation_follow_up_enabled
        )
        self._continuation_phrases = (
            continuation_phrases
            if continuation_phrases is not None
            else get_continuation_phrases()
        )

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

        if directly_addressed or intent.mentions_bot:
            if not mention_warrants_reply(
                text,
                should_reply=None,
                reply_to_bot=reply_to_bot,
            ):
                # A mention that is a status remark, unsolicited observation,
                # third-party talk, or closer should not even reach the
                # planner — it is treated like side talk.
                return PrefilterVerdict(False, "side_talk")
            return PrefilterVerdict(
                True,
                "direct_address" if directly_addressed else "bot_name",
            )

        # Sender-aware continuation follow-up: a short demand right after the
        # bot's own reply from the same user ("а ещё" = "tell me another one")
        # is an explicit request even when the post-reply listen window has
        # expired because other people wrote in between.
        if (
            self._continuation_enabled
            and is_sender_continuation_demand(
                text,
                recent_messages,
                sender_telegram_id,
                phrases=self._continuation_phrases,
            )
        ):
            return PrefilterVerdict(True, "continuation")

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

        if (
            self._defer_questions
            and intent.has_question
            and not _thread_dismissed(recent_messages)
        ):
            # A question that is not deterministically addressed still gets
            # "considered": defer to the reaction gate (Tier-1 catches clear
            # questions instantly; the LLM tier decides the ambiguous tail)
            # instead of hard-dropping it as side_talk before any semantics.
            # A recent dismissal closes the thread — stay silent.
            return PrefilterVerdict(True, "question")

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
