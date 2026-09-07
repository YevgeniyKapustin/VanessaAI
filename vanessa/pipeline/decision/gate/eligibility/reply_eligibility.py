from __future__ import annotations

from vanessa.config.content import get_continuation_phrases
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentDetector
from vanessa.pipeline.decision.detectors.noise import NoiseFilter
from vanessa.pipeline.decision.detectors.triggers import TriggerKeywordChecker
from vanessa.pipeline.decision.gate.eligibility.eligibility_compose import (
    allows_compose as compose_is_allowed,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_compose import (
    should_block_compose as compose_should_block,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_ignore import (
    hard_ignore,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_prefilter import (
    soft_prefilter,
)
from vanessa.pipeline.decision.gate.eligibility.eligibility_types import (
    HardIgnoreResult,
    PrefilterVerdict,
    _drop,
    prefilter_tag_to_decision_reason,
)
from vanessa.pipeline.decision.gate.eligibility.user_ignore import ChatIgnoreRegistry

__all__ = [
    "HardIgnoreResult",
    "PrefilterVerdict",
    "ReplyEligibility",
    "prefilter_tag_to_decision_reason",
]


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
    ) -> PrefilterVerdict:
        context = DecisionContext(
            text=text,
            telegram_chat_id=telegram_chat_id,
            recent_messages=recent_messages,
            intent=self._intent.detect(text),
            sender_telegram_id=sender_telegram_id,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            addressing=addressing,
            in_listen_window=force_listen_window,
        )
        hard = self.hard_ignore(context)
        if hard is not None:
            return _drop(hard.tag)
        return soft_prefilter(
            context,
            triggers=self._triggers,
            noise=self._noise,
            post_reply_listen_count=self._post_reply_listen_count,
            post_reply_listen_idle_seconds=self._post_reply_listen_idle_seconds,
            continuation_enabled=self._continuation_enabled,
            continuation_phrases=self._continuation_phrases,
            defer_questions=self._defer_questions,
        )

    def hard_ignore(self, context: DecisionContext) -> HardIgnoreResult | None:
        return hard_ignore(
            context,
            intent_detector=self._intent,
            ignore_registry=self._ignore_registry,
        )

    def allows_compose(
        self,
        context: DecisionContext,
        *,
        humor_ok: bool = False,
    ) -> bool:
        return compose_is_allowed(context, humor_ok=humor_ok)

    def should_block_compose(
        self,
        context: DecisionContext,
        *,
        humor_ok: bool = False,
    ) -> bool:
        return compose_should_block(
            context,
            intent_detector=self._intent,
            humor_ok=humor_ok,
        )
