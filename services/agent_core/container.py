from __future__ import annotations

from dataclasses import dataclass

from vanessa.config.content import get_bot_name_aliases, get_content, get_trigger_keywords
from vanessa.config.conversation_config import load_conversation_config
from vanessa.config.settings import settings
from vanessa.pipeline.decision import (
    IntentDetector,
    NoiseFilter,
    RateLimiter,
    SessionWindowAnalyzer,
    TriggerKeywordChecker,
)
from vanessa.pipeline.decision.gate.reply_eligibility import ReplyEligibility
from vanessa.pipeline.decision.gate.user_ignore import ChatIgnoreRegistry
from vanessa.pipeline.decision.gate.prefilter import PlannerPrefilter
from vanessa.pipeline.decision.gate.reaction_gate import ReactionGate
from vanessa.pipeline.llm.providers.protocols import create_chat_completer
from vanessa.pipeline.llm.memes import MemeCatalog, MemeDecider


from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    KnowledgeVectorStoreProtocol,
    VectorStoreProtocol,
)
from vanessa.infrastructure.runtime.vector_stores import (
    create_embedding_provider,
    create_knowledge_vector_store,
    create_message_vector_store,
)
from vanessa.pipeline.background import BackgroundExecutor


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
    reaction_gate: ReactionGate
    block_consecutive_replies: bool
    embedding_provider: EmbeddingProviderProtocol
    vector_store: VectorStoreProtocol
    knowledge_vector_store: KnowledgeVectorStoreProtocol
    meme_catalog: MemeCatalog
    meme_decider: MemeDecider
    background: BackgroundExecutor


_container: AppContainer | None = None


def build_app_container() -> AppContainer:
    conversation = load_conversation_config()
    content = get_content()
    memes_content = content.memes
    meme_catalog = MemeCatalog(memes_content)
    meme_decider = MemeDecider(
        enabled=memes_content.enabled,
        probability=memes_content.probability,
        min_messages_between=memes_content.min_messages_between,
    )
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
        reaction_gate=ReactionGate(content, llm_client=create_chat_completer()),
        block_consecutive_replies=content.decision.block_consecutive_replies,
        embedding_provider=create_embedding_provider(),
        vector_store=create_message_vector_store(),
        knowledge_vector_store=create_knowledge_vector_store(),
        meme_catalog=meme_catalog,
        meme_decider=meme_decider,
        background=BackgroundExecutor(
            maxsize=settings.background_queue_size,
            workers=settings.background_workers,
        ),
    )


def get_app_container() -> AppContainer:
    global _container
    if _container is None:
        _container = build_app_container()
    return _container


def reset_app_container() -> None:
    global _container
    _container = None
