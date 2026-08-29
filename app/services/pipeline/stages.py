import logging
import time

from app.config.content import get_content, get_photo_placeholder
from app.config.settings import settings
from app.core.messages import (
    ContextMessage,
    ImageAttachment,
    PhotoCandidate,
    stored_to_context,
)
from app.core.protocols import (
    ContextRetrieverProtocol,
    LLMProviderProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    TurnMetricsProtocol,
    UnitOfWorkProtocol,
)
from app.core.request_context import get_request_id
from app.core.turn import ConversationTurnResult
from app.decision.models import DecisionAction, DecisionReason, DecisionResult
from app.decision.gate.ignore_registry_protocol import ChatIgnoreRegistryProtocol
from app.decision.repeated_question import is_repeated_message
from app.decision.repeated_loop import LoopRegistry, loop_registry as default_loop_registry
from app.decision.gate.protocols import (
    PlannerPrefilterProtocol,
    ReactionGateProtocol,
    TurnPlannerProtocol,
)
from app.decision.protocols import DecisionEngineProtocol
from app.knowledge.entities import is_person_focused
from app.knowledge.metrics.feedback import (
    render_annoyance_note,
    render_feedback_block,
)
from app.knowledge.metrics.retriever import MetricsRetriever
from app.knowledge.retriever import KnowledgeRetriever
from app.llm.format.answer_tag import (
    extract_ignore_reason,
    has_ignore_marker,
    strip_control_tags,
)
from app.llm.format.message_blocks import split_reply_into_blocks, strip_block_markers
from app.llm.format.photo_tag import extract_photo_index
from app.llm.format.reply_format import strip_trailing_periods
from app.llm.format.sticker_tag import extract_sticker_tag
from app.llm.photo_request import is_photo_request
from app.llm.planner.turn_planner import TurnPlan
from app.llm.prompts.session_format import session_context_messages
from app.observability.metrics import (
    record_photo_request_missed,
    record_photo_send,
    record_web_search,
)
from app.rag.search.react_retriever import retrieve_with_react
from app.rag.search.search_plan import build_main_rag_plan
from app.services.humor_pipeline import HumorPipelineProtocol
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
from app.services.websearch.protocols import WebSearchService
from app.llm.memes import MemeCatalog, MemeDecider
from app.services.pipeline.gate_support import (
    apply_owner_ignore_if_needed,
    decision_reason_from_prefilter_tag,
    finish_decision_ignore,
    finish_ignore_turn,
    index_user_on_ignore,
)

logger = logging.getLogger(__name__)


class GateStage:
    def __init__(
        self,
        query_rewriter: TurnPlannerProtocol,
        decision_engine: DecisionEngineProtocol,
        planner_prefilter: PlannerPrefilterProtocol | None,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
        messages: MessageRepositoryProtocol,
        indexing: MessageIndexingSchedulerProtocol,
        ignore_registry: ChatIgnoreRegistryProtocol,
        metrics_retriever: MetricsRetriever | None = None,
        reaction_gate: ReactionGateProtocol | None = None,
        loop_registry: LoopRegistry | None = None,
    ) -> None:
        self._planner = query_rewriter
        self._decision = decision_engine
        self._prefilter = planner_prefilter
        self._loop_registry = loop_registry or default_loop_registry
        # Lightweight pre-planner classifier: when it says the message does not
        # need a reaction, the turn is finalized immediately and the expensive
        # LLM planner is never invoked.
        self._reaction_gate = reaction_gate
        self._config = config
        self._metrics = metrics
        self._messages = messages
        self._indexing = indexing
        self._ignore_registry = ignore_registry
        self._metrics_retriever = metrics_retriever

    async def run(self, ctx: TurnPipelineContext) -> bool:
        await apply_owner_ignore_if_needed(self._ignore_registry, ctx)

        # Bare caption-less photo ("[фото]" placeholder): Vanessa is NOT obliged
        # to reply to every photo, and a photo she does not answer is not even
        # analyzed (never sent to the vision model). She responds to a bare photo
        # only when she is actively listening (recently talked with her —
        # ``in_listen_window``) or the photo is addressed to her (a reply to her
        # message / a mention). Otherwise the turn is finalized as an IGNORE here,
        # before any prefilter/planner/vision cost.
        if ctx.turn.has_image and settings.vision_enabled:
            # Rollback toggle: restore the old "reply to ANY photo" behavior.
            if settings.vision_reply_to_any_photo:
                return await self._force_vision_turn(ctx)
            if ctx.turn.message.strip() == get_photo_placeholder():
                assert ctx.session is not None
                if (
                    ctx.session.in_listen_window
                    or ctx.turn.mentions_bot
                    or ctx.turn.reply_to_bot
                ):
                    return await self._force_vision_turn(ctx)
                await finish_ignore_turn(
                    ctx,
                    reason=DecisionReason.NOT_EXPECTED.value,
                    metrics=self._metrics,
                    indexing=self._indexing,
                    config=self._config,
                    planner_skipped=True,
                    log_event="turn_stage bare_photo_not_addressed",
                )
                return False

        # Captioned photos flow through the normal gate pipeline (prefilter,
        # reaction gate, planner, decision engine) like any text message — the
        # caption is real content. Only when the pipeline decides REPLY does the
        # compose stage attach the image to the vision model.
        if (
            self._config.planner_prefilter_enabled
            and self._prefilter is not None
        ):
            prefilter = self._prefilter.evaluate(
                ctx.turn.message,
                ctx.recent,
                telegram_chat_id=ctx.turn.telegram_chat_id,
                sender_telegram_id=ctx.turn.sender_telegram_id,
                mentions_bot=ctx.turn.mentions_bot,
                reply_to_bot=ctx.turn.reply_to_bot,
                reply_to_other_user=ctx.turn.reply_to_other_user,
            )
            if not prefilter.run_planner:
                ctx.planner_skipped = True
                await finish_ignore_turn(
                    ctx,
                    reason=decision_reason_from_prefilter_tag(prefilter.reason),
                    metrics=self._metrics,
                    indexing=self._indexing,
                    config=self._config,
                    planner_skipped=True,
                    log_event="turn_stage prefilter",
                )
                return False

        # Lightweight Decision Gate (reaction classifier): one fast, cheap
        # YES/NO call right before the expensive LLM turn planner. When the
        # answer is NO (people chatting among themselves, the bot's name
        # mentioned in passing, small talk), the turn is finalized instantly
        # and the planner/RAG/compose chain is never invoked.
        if self._reaction_gate is not None:
            assert ctx.session is not None
            gate_started = time.perf_counter()
            reaction = await self._reaction_gate.evaluate(
                ctx.turn.message,
                ctx.recent,
                mentions_bot=ctx.turn.mentions_bot,
                reply_to_bot=ctx.turn.reply_to_bot,
                reply_to_other_user=ctx.turn.reply_to_other_user,
                in_listen_window=ctx.session.in_listen_window,
                sender_telegram_id=ctx.turn.sender_telegram_id,
            )
            ctx.reaction_gate_ms = (time.perf_counter() - gate_started) * 1000
            logger.info(
                "turn_stage reaction_gate request_id=%s respond=%s reason=%s "
                "reaction_gate_ms=%.1f",
                get_request_id(),
                reaction.respond,
                reaction.reason,
                ctx.reaction_gate_ms,
            )
            if not reaction.respond:
                ctx.planner_skipped = True
                await finish_ignore_turn(
                    ctx,
                    reason=DecisionReason.REACTION_GATE.value,
                    metrics=self._metrics,
                    indexing=self._indexing,
                    config=self._config,
                    planner_skipped=True,
                    log_event="turn_stage reaction_gate",
                )
                return False

        rewrite_started = time.perf_counter()
        assert ctx.session is not None
        ctx.turn_plan = await self._planner.prepare(
            ctx.turn.message,
            recent_messages=ctx.recent,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            reply_to_other_user=ctx.turn.reply_to_other_user,
            in_listen_window=ctx.session.in_listen_window,
        )
        ctx.plan_ms = (time.perf_counter() - rewrite_started) * 1000

        if self._metrics_retriever is not None:
            try:
                ctx.sender_profile = await self._metrics_retriever.get_by_telegram_id(
                    ctx.turn.sender_telegram_id
                )
            except Exception:
                logger.exception("metrics_retrieve_failed")
                ctx.sender_profile = None

        # Loop-repetition signal: the same sender re-asking the SAME topic with
        # different words raises Vanessa's annoyance (drives LowAttitudeRule —
        # maximal ignore tendency — and the cold compose note).
        if ctx.turn_plan is not None:
            signal = self._loop_registry.update(
                ctx.turn.sender_telegram_id,
                ctx.turn.message,
                ctx.recent,
                planner_repeated=ctx.turn_plan.repeated_topic,
                planner_loop_level=ctx.turn_plan.loop_level,
                window=settings.decision_loop_window,
                similarity_threshold=settings.decision_loop_similarity_threshold,
                decay_half_life_seconds=settings.decision_loop_decay_half_life_seconds,
            )
            ctx.loop_strength = signal.loop_strength
            ctx.annoyance = signal.annoyance

        decision_started = time.perf_counter()
        ctx.decision = await self._decision.decide(
            text=ctx.turn.message,
            telegram_chat_id=ctx.turn.telegram_chat_id,
            recent_messages=ctx.recent,
            search_text=ctx.turn_plan.text if not ctx.turn_plan.skip_search else "",
            should_reply=ctx.turn_plan.should_reply,
            mentions_bot=ctx.turn.mentions_bot,
            reply_to_bot=ctx.turn.reply_to_bot,
            reply_to_other_user=ctx.turn.reply_to_other_user,
            in_listen_window=ctx.session.in_listen_window,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            sender_metrics=ctx.sender_metrics,
            humor_ok=ctx.turn_plan.humor_ok,
            loop_strength=ctx.loop_strength,
            annoyance=ctx.annoyance,
        )
        ctx.decision_ms = (time.perf_counter() - decision_started) * 1000

        logger.info(
            "turn_stage plan request_id=%s search=%r skip=%s should_reply=%s "
            "humor_ok=%s humor_query=%r deep_search=%s listen_window=%s "
            "needs_clarification=%s detail=%s reaction_gate_ms=%.1f plan_ms=%.1f "
            "decision_ms=%.1f action=%s reason=%s",
            get_request_id(),
            ctx.turn_plan.text,
            ctx.turn_plan.skip_search,
            ctx.turn_plan.should_reply,
            ctx.turn_plan.humor_ok,
            ctx.turn_plan.humor_query,
            ctx.turn_plan.deep_search,
            ctx.session.in_listen_window,
            ctx.turn_plan.needs_clarification,
            ctx.turn_plan.detail,
            ctx.reaction_gate_ms,
            ctx.plan_ms,
            ctx.decision_ms,
            ctx.decision.action.value,
            ctx.decision.reason.value,
        )

        if ctx.decision.action == DecisionAction.IGNORE:
            await finish_decision_ignore(
                ctx,
                metrics=self._metrics,
                indexing=self._indexing,
                config=self._config,
            )
            return False

        return True

    async def _force_vision_turn(self, ctx: TurnPipelineContext) -> bool:
        """Vision reply path for a bare photo the gate decided to answer.

        Called only when Vanessa is actively listening (``in_listen_window``) or
        the photo is addressed to her (a reply to her message / a mention), or
        when the ``vision_reply_to_any_photo`` rollback toggle is on. Skips the
        text planner (a bare photo has nothing useful to classify) and builds a
        forced ``TurnPlan`` + REPLY ``DecisionResult`` so the turn proceeds to
        Retrieve/Compose, where the vision model describes the image.
        ``FinalizeStage`` asserts a non-None decision, so the forced decision is
        required here.
        """
        if self._metrics_retriever is not None:
            try:
                ctx.sender_profile = await self._metrics_retriever.get_by_telegram_id(
                    ctx.turn.sender_telegram_id
                )
            except Exception:
                logger.exception("metrics_retrieve_failed")
                ctx.sender_profile = None
        message = ctx.turn.message.strip()
        ctx.turn_plan = TurnPlan(
            original=ctx.turn.message,
            text=message or "(описание фото)",
            skip_search=True,
            should_reply=True,
        )
        ctx.decision = DecisionResult(
            action=DecisionAction.REPLY,
            reason=DecisionReason.FORCE_REPLY,
            relevance_score=1.0,
        )
        ctx.plan_ms = 0.0
        ctx.decision_ms = 0.0
        logger.info(
            "turn_stage vision_forced request_id=%s chat_id=%s text=%r images=%s",
            get_request_id(),
            ctx.turn.telegram_chat_id,
            ctx.turn.message,
            len(ctx.turn.images),
        )
        return True


class RetrieveStage:
    def __init__(
        self,
        retriever: ContextRetrieverProtocol,
        humor_pipeline: HumorPipelineProtocol,
        uow: UnitOfWorkProtocol | None,
        knowledge: KnowledgeRetriever | None = None,
        meme_catalog: MemeCatalog | None = None,
        meme_decider: MemeDecider | None = None,
        web_search: WebSearchService | None = None,
    ) -> None:
        self._retriever = retriever
        self._humor = humor_pipeline
        self._uow = uow
        self._knowledge = knowledge
        self._meme_catalog = meme_catalog
        self._meme_decider = meme_decider
        # Live web search (the "googling" skill); None disables it (default).
        self._web_search = web_search

    async def run(self, ctx: TurnPipelineContext) -> bool:
        if self._uow is not None:
            await self._uow.commit()

        assert ctx.turn_plan is not None
        if not ctx.turn_plan.skip_search and build_main_rag_plan(
            ctx.turn.message,
            ctx.turn_plan,
        ).semantic_queries:
            embed_started = time.perf_counter()
            ctx.embed_ms = (time.perf_counter() - embed_started) * 1000

        # Semantic archive (People/Lore/Culture/Logs) is the primary RAG source —
        # those notes are already semantic summaries, unlike raw message history.
        semantic_query = self._semantic_query(ctx.turn_plan, ctx.turn.message)

        # Deterministic participant resolution: which People dossiers are
        # relevant to this turn (mentioned in the message + recent window).
        # This powers multi-person retrieval — all mentioned people get pulled,
        # not a single arbitrary match.
        people_files: list[str] = []
        if self._knowledge is not None:
            try:
                people_files = await self._knowledge.resolve_people(
                    ctx.turn.message,
                    ctx.recent,
                )
            except Exception:
                logger.exception("people_resolve_failed, ignoring")
                people_files = []

        # Deterministic fallback: if the message is clearly about people and the
        # planner (LLM) omitted the "people" index, force it — the resolver is
        # cheap and exact, the planner is not.
        knowledge_indexes = list(ctx.turn_plan.knowledge_indexes)
        if (
            people_files
            and "people" not in knowledge_indexes
            and is_person_focused(ctx.turn.message)
        ):
            knowledge_indexes.append("people")
            logger.info(
                "people_index_forced_by_resolver files=%s",
                sorted(people_files),
            )

        semantic_started = time.perf_counter()
        semantic_found = False
        if self._knowledge is not None:
            try:
                ctx.knowledge_blocks = await self._knowledge.fetch_semantic(
                    semantic_query,
                    knowledge_indexes=tuple(knowledge_indexes),
                    knowledge_query=ctx.turn_plan.knowledge_query,
                    humor_ok=ctx.turn_plan.humor_ok,
                    humor_query=ctx.turn_plan.humor_query,
                    user_message=ctx.turn.message,
                    people_detail=ctx.turn_plan.knowledge_detail,
                    people_files=people_files or None,
                )
            except Exception:
                # Fail-open: a semantic-search failure (e.g. Qdrant down) must
                # never block the turn — fall back to raw-message RAG.
                logger.exception(
                    "semantic_search_failed query=%r, using raw RAG fallback",
                    semantic_query,
                )
                ctx.knowledge_blocks = []
            semantic_found = bool(ctx.knowledge_blocks)
        ctx.semantic_ms = (time.perf_counter() - semantic_started) * 1000

        rag_started = time.perf_counter()
        # Raw-message history is only a fallback: run it when the archive had
        # nothing relevant, or as an extra pass for deep multi-step searches.
        if not semantic_found or ctx.turn_plan.deep_search:
            ctx.context_blocks = await retrieve_with_react(
                self._retriever,
                ctx.turn.message,
                ctx.turn_plan,
            )
        ctx.rag_ms = (time.perf_counter() - rag_started) * 1000

        # Live web search (the "googling" skill): runs alongside RAG when the
        # planner flagged the turn. Fail-open — results only ever enrich the
        # compose prompt, never block the reply.
        await self._run_web_search(ctx)

        humor_started = time.perf_counter()
        ctx.humor_quotes = await self._humor.fetch_quotes(
            ctx.turn_plan,
            ctx.turn.message,
        )
        ctx.humor_rag_ms = (time.perf_counter() - humor_started) * 1000

        if ctx.humor_quotes:
            logger.info(
                "turn_stage humor_rag request_id=%s humor_query=%r quotes=%s "
                "humor_rag_ms=%.1f",
                get_request_id(),
                ctx.turn_plan.humor_query,
                len(ctx.humor_quotes),
                ctx.humor_rag_ms,
            )

        # Curated memes (hybrid): when the planner allows humor, a keyword match
        # offers that specific meme; otherwise (if enabled) a compact menu is
        # offered so the bot can pick a meme itself. Both paths pass the same
        # anti-spam gate (probability + per-chat cooldown).
        if (
            ctx.turn_plan is not None
            and ctx.turn_plan.humor_ok
            and self._meme_catalog is not None
            and self._meme_decider is not None
            and self._meme_catalog.enabled
        ):
            matched = self._meme_catalog.match(ctx.turn.message)
            if matched:
                if self._meme_decider.decide(ctx.turn.telegram_chat_id):
                    ctx.meme_blocks = matched
                    self._meme_decider.register_meme(ctx.turn.telegram_chat_id)
            elif self._meme_catalog.offer_on_humor:
                if self._meme_decider.decide(ctx.turn.telegram_chat_id):
                    ctx.meme_menu = self._meme_catalog.offerable()
                    self._meme_decider.register_meme(ctx.turn.telegram_chat_id)

        logger.info(
            "turn_stage rag request_id=%s context=%s semantic_found=%s "
            "deep_search=%s knowledge=%s meme_blocks=%s meme_menu=%s "
            "semantic_ms=%.1f rag_ms=%.1f",
            get_request_id(),
            ctx.context_count,
            semantic_found,
            ctx.turn_plan.deep_search,
            len(ctx.knowledge_blocks),
            len(ctx.meme_blocks),
            len(ctx.meme_menu),
            ctx.semantic_ms,
            ctx.rag_ms,
        )
        return True

    async def _run_web_search(self, ctx: TurnPipelineContext) -> None:
        """Run the live web search when the planner flagged the turn.

        Fail-open by design: a search error or an empty result never blocks the
        turn — the composer simply answers from the archive / its own knowledge.
        Timing and outcome are recorded so search quality is observable.
        """
        assert ctx.turn_plan is not None
        if not settings.web_search_enabled or self._web_search is None:
            return
        query = (ctx.turn_plan.web_query or "").strip()
        if not ctx.turn_plan.web_search or not query:
            return
        started = time.perf_counter()
        try:
            results = await self._web_search.search(
                query,
                limit=settings.web_search_max_results,
            )
            ctx.web_blocks = list(results)
            status = "found" if results else "empty"
        except Exception:
            # Fail-open: never let a broken search API block the reply.
            logger.exception(
                "web_search_failed request_id=%s query=%r",
                get_request_id(),
                query,
            )
            ctx.web_blocks = []
            status = "error"
        ctx.web_ms = (time.perf_counter() - started) * 1000
        record_web_search(status, ctx.web_ms)
        logger.info(
            "turn_stage web_search request_id=%s query=%r results=%s web_ms=%.1f",
            get_request_id(),
            query,
            len(ctx.web_blocks),
            ctx.web_ms,
        )

    @staticmethod
    def _semantic_query(turn_plan, message: str) -> str:
        """Prefer the composed archive query, then the embedding query, then raw."""
        for candidate in (turn_plan.knowledge_query, turn_plan.text):
            if candidate and candidate.strip():
                return candidate.strip()
        return message.strip()


def _collect_turn_images(ctx: TurnPipelineContext) -> list[ImageAttachment]:
    """Assemble the images for a vision turn.

    Current-turn images come first; then attachments from prior session messages
    (newest first, excluding the current message — it already contributes via
    ``ctx.turn.images``) so follow-ups like "а переведи вон ту надпись на ней"
    can reference an earlier photo. Bounded by ``vision_session_images`` per
    session and ``vision_max_images_per_turn`` overall.
    """
    images: list[ImageAttachment] = list(ctx.turn.images)
    prior = ctx.recent[:-1] if ctx.recent else []
    session_count = 0
    session_limit = settings.vision_session_images
    max_total = settings.vision_max_images_per_turn
    for message in reversed(prior):
        if session_count >= session_limit or len(images) >= max_total:
            break
        for attachment in message.attachments:
            if not attachment.data_url:
                continue
            images.append(attachment)
            session_count += 1
            if session_count >= session_limit or len(images) >= max_total:
                break
    return images[:max_total]


def _photo_caption_for(message) -> str:
    """Best human label of a photo message for the album list."""
    if message.photo_caption and message.photo_caption.strip():
        return message.photo_caption.strip()
    content = (message.content or "").strip()
    if content and content != get_photo_placeholder():
        return content
    return get_photo_placeholder()


def _collect_photo_candidates(
    ctx: TurnPipelineContext,
    photo_messages: list[ContextMessage] | None = None,
) -> list[PhotoCandidate]:
    """Assemble the "photo album" — photos the bot could re-send.

    Candidates come from three sources, all meaning-driven:
    - ``photo_messages`` — the dedicated photo-by-meaning search
      (``search_photo_messages`` FTS over the caption-inclusive search_vector)
      run against the REWRITTEN query, so a photo is found by the MEANING of
      the turn ("скинь то фото где кот" -> the caption "рыжий кот на диване"),
      not by the literal words the user typed;
    - messages the RAG retrieval surfaced for THIS turn (``ctx.context_blocks``) —
      the "по смыслу" leg (photo captions are folded into the FTS search_vector);
    - recent session messages with attachments (so "верни то фото" without a
      precise query still works).
    Deduplicated by telegram_file_id and bounded by ``vision_photo_candidates``.
    """
    seen: set[str] = set()
    # (file_id, data_url, caption, sender, msg)
    collected: list[tuple[str, str, str, str, object]] = []
    # The current turn's own images are already attached (``current_images`` /
    # ``images``) — never offer them again as re-sendable album entries.
    current_file_ids = {
        attachment.telegram_file_id
        for attachment in ctx.turn.images
        if attachment.telegram_file_id
    }

    def _add(message) -> None:
        for attachment in message.attachments:
            file_id = attachment.telegram_file_id
            if not file_id or file_id in seen or file_id in current_file_ids:
                continue
            seen.add(file_id)
            collected.append(
                (
                    file_id,
                    attachment.data_url or "",
                    _photo_caption_for(message),
                    message.sender_name or "",
                    message,
                )
            )

    # Meaning-search hits first (the strongest "по смыслу" match), then the RAG
    # context (meaning match), then the recent session (recency).
    for message in photo_messages or []:
        _add(message)
    for block in ctx.context_blocks:
        for message in block.messages:
            _add(message)
    for message in ctx.recent:
        _add(message)

    candidates: list[PhotoCandidate] = []
    for index, (file_id, data_url, caption, sender, message) in enumerate(
        collected, start=1
    ):
        if len(candidates) >= settings.vision_photo_candidates:
            break
        candidates.append(
            PhotoCandidate(
                index=index,
                telegram_file_id=file_id,
                caption=caption,
                sender_name=sender or None,
                created_at=getattr(message, "created_at", None),
                data_url=data_url or None,
            )
        )
    return candidates


class ComposeStage:
    def __init__(
        self,
        llm: LLMProviderProtocol,
        *,
        refuse_enabled: bool = True,
        refuse_min_occurrences: int = 2,
        messages: MessageRepositoryProtocol | None = None,
    ) -> None:
        self._llm = llm
        self._refuse_enabled = refuse_enabled
        self._refuse_min_occurrences = max(2, refuse_min_occurrences)
        # Message repo used for the meaning-driven photo-album search
        # (``search_photo_messages``): finds photo messages whose caption matches
        # the MEANING of the turn, not the literal text the user typed.
        self._messages = messages

    async def run(self, ctx: TurnPipelineContext) -> bool:
        # Compose-stage refusal, defense-in-depth for spam: the gate usually
        # catches repeats, but some paths never run the decision engine (the
        # vision forced-turn path) or could be bypassed in the future. Re-check
        # deterministically here, at the very moment of preparing the answer, so
        # the expensive LLM is not even invoked for an identical spam burst.
        # A bare caption-less photo carries only the placeholder ("[фото]") — not
        # real content — so two consecutive photos must never be mistaken for a
        # repeated-message spam burst (they normalize to the same token). The
        # repeat check still applies to captioned photos and text.
        bare_photo = (
            ctx.turn.has_image
            and ctx.turn.message.strip() == get_photo_placeholder()
        )
        if self._refuse_enabled and not bare_photo and is_repeated_message(
            ctx.turn.message,
            ctx.recent,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            min_occurrences=self._refuse_min_occurrences,
        ):
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_repeated",
            )

        llm_started = time.perf_counter()
        session_messages = session_context_messages(ctx.recent)
        # The notes must name the sender EXACTLY as the current <msg sender="...">
        # does (ctx.sender_name — the same resolved display name), so the model
        # never has to reconcile two different names for one person (e.g. the
        # profile's «Гриша» vs the message's «Ну я») and burns chain-of-thought
        # guessing who the sender is.
        metrics_block = None
        if ctx.sender_profile is not None and ctx.sender_metrics is not None:
            metrics_block = render_feedback_block(
                name=ctx.sender_name,
                metrics=ctx.sender_metrics,
                mood=ctx.sender_profile.mood,
            )
        # Cold-reply note: a sender stuck in a same-topic loop gets a dry, sharp,
        # brief answer — no warmth, no fluff (the loop dropped Vanessa's attitude).
        attitude_note = None
        if (
            ctx.sender_profile is not None
            and ctx.annoyance >= settings.feedback_annoyance_threshold
        ):
            attitude_note = render_annoyance_note(
                name=ctx.sender_name,
                annoyance=ctx.annoyance,
            )
        # Vision: attach the current + recent-session images when enabled; the
        # provider routes the call to the vision model only when images are present.
        images = _collect_turn_images(ctx) if settings.vision_enabled else []
        # Did the user explicitly ask for a photo? Drives the honesty directives
        # (marker required / honest refusal) and the missed-request metric below.
        photo_requested = is_photo_request(ctx.turn.message)
        # Photo album: photos the bot could re-send, matched to the context by
        # RAG "по смыслу" + the recent session. The dedicated meaning-search leg
        # (``search_photo_messages``) finds photo messages whose caption matches
        # the REWRITTEN query — so a bare photo is found by the MEANING of the
        # turn ("скинь то фото где кот" -> the caption "рыжий кот на диване"),
        # not by the literal words the user typed. Fail-open: a search error
        # must never block the reply. The current turn's own photos are excluded
        # inside ``_collect_photo_candidates`` (they are already attached).
        photo_messages: list[ContextMessage] = []
        if (
            settings.vision_enabled
            and self._messages is not None
            and ctx.turn_plan is not None
        ):
            meaning_query = self._semantic_query(ctx.turn_plan, ctx.turn.message)
            try:
                stored = await self._messages.search_photo_messages(
                    meaning_query,
                    limit=settings.vision_photo_candidates * 2,
                )
                photo_messages = [stored_to_context(m) for m in stored]
            except Exception:
                logger.exception(
                    "photo_meaning_search_failed request_id=%s query=%r",
                    get_request_id(),
                    meaning_query,
                )
                photo_messages = []
        photo_candidates = (
            _collect_photo_candidates(ctx, photo_messages)
            if settings.vision_enabled
            else []
        )
        ctx.reply = await self._llm.generate(
            user_message=ctx.turn.message,
            context_blocks=ctx.context_blocks,
            session_messages=session_messages,
            humor_quotes=ctx.humor_quotes or None,
            knowledge_blocks=ctx.knowledge_blocks or None,
            web_blocks=ctx.web_blocks or None,
            meme_blocks=ctx.meme_blocks or None,
            meme_menu=ctx.meme_menu or None,
            metrics_block=metrics_block,
            attitude_note=attitude_note,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            sender_name=ctx.sender_name,
            tone=ctx.turn_plan.tone,
            needs_clarification=ctx.turn_plan.needs_clarification,
            clarification_hint=ctx.turn_plan.clarification_hint,
            detail=ctx.turn_plan.detail,
            uses_pro_model=ctx.turn_plan.uses_pro_model,
            reply_to_text=ctx.turn.reply_to_text,
            reply_to_sender_telegram_id=ctx.turn.reply_to_sender_telegram_id,
            reply_to_sender_name=ctx.turn.reply_to_sender_name,
            images=images or None,
            photo_candidates=photo_candidates or None,
            # The current message's OWN images render inside its <msg> as
            # <attachment> children (all photos stay with the text), so the
            # model never loses which photo goes with which caption. ``images``
            # (incl. prior-session vision) stays separate — it feeds the vision
            # model, not the current <msg>.
            current_images=list(ctx.turn.images) or None,
        )
        # The compose model is instructed to output the tag `[ignore]` (plus an
        # optional short debug-only reason after it — never an `[answer]` or a
        # message) when the user repeats the same thing — an explicit refusal
        # signal, far more robust than an empty reply. Honor it here (at the
        # moment of preparing the answer) instead of letting it flow through as
        # a literal `[ignore]` message.
        if self._refuse_enabled and has_ignore_marker(ctx.reply or ""):
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_marker",
                # The model writes a short reason after the tag (e.g.
                # `[ignore] повтор того же вопроса`) purely for debugging — it
                # is never delivered to the chat.
                detail=extract_ignore_reason(ctx.reply),
            )
        # Fallback: an empty reply is also treated as the model staying silent
        # (older prompt / the model forgetting the marker). Previously an empty
        # reply still created an empty assistant message and a recorded REPLY
        # turn — the bot "replied" with nothing while believing it answered.
        if self._refuse_enabled and not (ctx.reply or "").strip():
            return self._refuse(
                ctx,
                reason=DecisionReason.REPEATED.value,
                log_event="turn_stage compose_refuse_empty",
            )
        # Resolve the [photo:<index>] marker the model may have emitted: strip it
        # from the reply and remember the file_id the bot should re-send.
        clean_reply, photo_index = extract_photo_index(ctx.reply)
        if photo_index is not None:
            if 1 <= photo_index <= len(photo_candidates):
                candidate = photo_candidates[photo_index - 1]
                ctx.photo_file_id = candidate.telegram_file_id
                # Carry the stored bytes so the bot can fall back to an upload
                # if the Telegram file_id is stale when it tries to re-send.
                ctx.photo_data_url = candidate.data_url
                logger.info(
                    "photo_send_resolved request_id=%s index=%s file_id=%s",
                    get_request_id(),
                    photo_index,
                    ctx.photo_file_id,
                )
            else:
                logger.warning(
                    "photo_send_index_out_of_range request_id=%s index=%s total=%s",
                    get_request_id(),
                    photo_index,
                    len(photo_candidates),
                )
            ctx.reply = clean_reply

        # Honesty + observability: a photo request that resolved to no delivery
        # is exactly the "сказала что отправила, но фото не пришло" bug. When the
        # user asked for a photo and we end up with no photo_file_id, record the
        # failure with a reason so it can be monitored and investigated.
        if ctx.photo_file_id:
            record_photo_send("resolved")
        elif photo_requested:
            if photo_index is not None:
                reason = "index_out_of_range"
            elif photo_candidates:
                reason = "no_marker"
            else:
                reason = "album_empty"
            record_photo_request_missed(reason)
            logger.warning(
                "photo_request_missed request_id=%s reason=%s candidates=%s",
                get_request_id(),
                reason,
                len(photo_candidates),
            )
        ctx.llm_ms = (time.perf_counter() - llm_started) * 1000
        logger.info(
            "turn_stage llm request_id=%s reply_len=%s llm_ms=%.1f",
            get_request_id(),
            len(ctx.reply),
            ctx.llm_ms,
        )
        return True

    @staticmethod
    def _semantic_query(turn_plan, message: str) -> str:
        """Prefer the composed archive query, then the embedding query, then raw.

        Shared with ``RetrieveStage``: the photo-by-meaning search must run on
        the REWRITTEN query (the MEANING of the turn), not the literal message
        the user typed — that is what makes a bare photo (whose caption carries
        the meaning) findable "по смыслу".
        """
        for candidate in (turn_plan.knowledge_query, turn_plan.text):
            if candidate and candidate.strip():
                return candidate.strip()
        return message.strip()

    def _refuse(
        self,
        ctx: TurnPipelineContext,
        *,
        reason: str,
        log_event: str,
        detail: str = "",
    ) -> bool:
        """Refuse the answer at compose time.

        Drops the (already generated or never-started) reply and returns False so
        the orchestrator finalizes the turn as an IGNORE via ``FinalizeStage.skip``
        — the user message is still indexed, no assistant message is created and
        nothing is delivered to the chat. ``detail`` is an optional extra debug
        context (e.g. the model's reason written after the ``[ignore]`` marker);
        it is only logged, never sent anywhere.
        """
        ctx.reply = None
        ctx.refuse_reason = reason
        logger.info(
            "%s request_id=%s reason=%s ignore_reason=%r sender_id=%s text=%r",
            log_event,
            get_request_id(),
            reason,
            detail,
            ctx.turn.sender_telegram_id,
            ctx.turn.message,
        )
        return False


class FinalizeStage:
    def __init__(
        self,
        messages: MessageRepositoryProtocol,
        indexing: MessageIndexingSchedulerProtocol,
        decision_engine: DecisionEngineProtocol,
        config: OrchestratorConfig,
        metrics: TurnMetricsProtocol,
        meme_decider: MemeDecider | None = None,
    ) -> None:
        self._messages = messages
        self._indexing = indexing
        self._decision = decision_engine
        self._config = config
        self._metrics = metrics
        self._meme_decider = meme_decider

    async def skip(self, ctx: TurnPipelineContext, *, reason: str) -> None:
        """Finish the turn without a reply.

        Used when a later stage decides the user's message does not need a
        reply. The user message is still indexed and the turn is recorded as
        ignored (no assistant message is created, no reply is registered).
        """
        await index_user_on_ignore(ctx, self._indexing, self._config)
        ctx.result = ConversationTurnResult(
            action=DecisionAction.IGNORE.value,
            reason=reason,
            relevance_score=(
                ctx.decision.relevance_score if ctx.decision is not None else 0.0
            ),
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
        )

    async def run(self, ctx: TurnPipelineContext) -> bool:
        assert ctx.user_msg is not None
        assert ctx.decision is not None
        assert ctx.turn_plan is not None
        assert ctx.reply is not None

        if self._config.defer_index_on_ignore:
            self._indexing.schedule(ctx.user_msg)
        else:
            await self._indexing.index_now(ctx.user_msg)

        clean_reply, sticker_tag = extract_sticker_tag(ctx.reply)
        # Final control-tag safety net: a reasoning model may emit [answer] /
        # <answer> / [ignore] in a form the provider's splitter missed — never
        # let a control tag reach the chat. The [next] block marker is left for
        # the block splitter below, which needs it to separate the messages.
        clean_reply = strip_control_tags(clean_reply)
        # Split the reply into the individual Telegram messages to send (on the
        # marker-containing text, so the model's explicit `[next]` blocks drive
        # the split; a deterministic sentence-aware split is the fallback when
        # the model skipped markers). The persona avoids a trailing period at the
        # end of a message, so it is cut deterministically from EVERY delivered
        # block (not just the overall reply); the marker-free full text is what
        # stays in the DB and metrics.
        marker = get_content().llm.block_marker
        messages = [
            block
            for block in (
                strip_trailing_periods(b)
                for b in split_reply_into_blocks(clean_reply, marker=marker)
            )
            if block.strip()
        ]
        clean_reply = strip_block_markers(clean_reply, marker=marker)
        ctx.reply = clean_reply

        await self._messages.create(
            role="assistant",
            content=clean_reply,
        )
        self._decision.record_reply(ctx.turn.telegram_chat_id)
        if self._meme_decider is not None:
            self._meme_decider.register_reply(ctx.turn.telegram_chat_id)

        ctx.result = ConversationTurnResult(
            action=ctx.decision.action.value,
            reason=ctx.decision.reason.value,
            reply=clean_reply,
            messages=messages,
            context_count=ctx.context_count,
            relevance_score=ctx.decision.relevance_score,
            sticker_tag=sticker_tag,
            # Photo the compose model asked to re-send (resolved from [photo:N]).
            photo_file_id=ctx.photo_file_id,
            # Stored bytes of the same photo, so the bot can fall back to an
            # upload when the Telegram file_id is stale at delivery time.
            photo_data_url=ctx.photo_data_url,
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
            deep_search=ctx.turn_plan.deep_search,
        )
        return True
