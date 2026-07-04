from __future__ import annotations

from dataclasses import dataclass

from app.config.content import get_bot_name_aliases, get_content, get_trigger_keywords
from app.config.conversation_config import load_conversation_config
from app.config.settings import settings
from app.decision import (
    IntentDetector,
    NoiseFilter,
    RateLimiter,
    SessionWindowAnalyzer,
    TriggerKeywordChecker,
)
from app.decision.gate.reply_eligibility import ReplyEligibility
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.gate.prefilter import PlannerPrefilter


@dataclass
class AppContainer:
    rate_limiter: RateLimiter
    ignore_registry: ChatIgnoreRegistry
    intent_detector: IntentDetector
    trigger_checker: TriggerKeywordChecker
    noise_filter: NoiseFilter
    session_analyzer: SessionWindowAnalyzer
    reply_eligibility: ReplyEligibility
    planner_prefilter: PlannerPrefilter
    block_consecutive_replies: bool


_container: AppContainer | None = None


def build_app_container() -> AppContainer:
    conversation = load_conversation_config()
    content = get_content()
    intent_detector = IntentDetector(bot_names=get_bot_name_aliases())
    trigger_checker = TriggerKeywordChecker(keywords=get_trigger_keywords())
    noise_filter = NoiseFilter()
    ignore_registry = ChatIgnoreRegistry()
    eligibility = ReplyEligibility(
        intent_detector,
        trigger_checker,
        noise_filter,
        ignore_registry,
        post_reply_listen_count=conversation.post_reply_listen_count,
        post_reply_listen_idle_seconds=conversation.session_idle_seconds,
    )
    return AppContainer(
        rate_limiter=RateLimiter(
            max_replies=settings.decision_rate_limit_per_minute,
            window_seconds=60,
        ),
        ignore_registry=ignore_registry,
        intent_detector=intent_detector,
        trigger_checker=trigger_checker,
        noise_filter=noise_filter,
        session_analyzer=SessionWindowAnalyzer(
            window_size=conversation.session_window_size,
            intent_detector=intent_detector,
            trigger_checker=trigger_checker,
        ),
        reply_eligibility=eligibility,
        planner_prefilter=PlannerPrefilter(eligibility),
        block_consecutive_replies=content.decision.block_consecutive_replies,
    )


def get_app_container() -> AppContainer:
    global _container
    if _container is None:
        _container = build_app_container()
    return _container


def reset_app_container() -> None:
    global _container
    _container = None
