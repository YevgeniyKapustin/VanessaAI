import logging
import time

from app.config.content import get_content
from app.config.settings import settings
from app.core.messages import ImageAttachment, PhotoCandidate
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
from app.llm.format.message_blocks import split_reply_into_blocks, strip_block_markers
from app.llm.format.photo_tag import extract_photo_index
from app.llm.format.reply_format import strip_trailing_periods
from app.llm.format.sticker_tag import extract_sticker_tag
from app.llm.planner.turn_planner import TurnPlan
from app.llm.prompts.session_format import session_context_messages
from app.rag.search.react_retriever import retrieve_with_react
from app.rag.search.search_plan import build_main_rag_plan
from app.services.humor_pipeline import HumorPipelineProtocol
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.context import TurnPipelineContext
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

        # Vision turns ("reply to any photo"): the empty/placeholder caption must
        # not be dropped by the prefilter/reaction-gate noise heuristics, and the
        # text-based planner has nothing useful to classify. A forced plan + REPLY
        # decision sends the turn straight to Retrieve/Compose for the vision model.
        if ctx.turn.has_image and settings.vision_enabled:
            return await self._force_vision_turn(ctx)

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
            "needs_clarification=%s reaction_gate_ms=%.1f plan_ms=%.1f "
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
        """Auto-reply path for image turns ("reply to any photo").

        Skips the prefilter/reaction-gate noise short-circuits (a bare photo has
        an empty/placeholder caption the heuristics would drop) and the text
        planner (nothing useful to classify). Builds a forced ``TurnPlan`` and a
        REPLY ``DecisionResult`` so the turn proceeds to Retrieve/Compose, where
        the vision model describes the image. ``FinalizeStage`` asserts a
        non-None decision, so the forced decision is required here.
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
    ) -> None:
        self._retriever = retriever
        self._humor = humor_pipeline
        self._uow = uow
        self._knowledge = knowledge
        self._meme_catalog = meme_catalog
        self._meme_decider = meme_decider

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
    if content and content != settings.vision_photo_placeholder:
        return content
    return settings.vision_photo_placeholder


def _collect_photo_candidates(ctx: TurnPipelineContext) -> list[PhotoCandidate]:
    """Assemble the "photo album" — photos the bot could re-send.

    Candidates come from two sources, both meaning-driven:
    - messages the RAG retrieval surfaced for THIS turn (``ctx.context_blocks``) —
      the "по смыслу" leg (photo captions are folded into the FTS search_vector);
    - recent session messages with attachments (so "верни то фото" without a
      precise query still works).
    Deduplicated by telegram_file_id and bounded by ``vision_photo_candidates``.
    """
    seen: set[str] = set()
    collected: list[tuple[str, str, str, object]] = []  # (file_id, caption, sender, msg)

    def _add(message) -> None:
        for attachment in message.attachments:
            file_id = attachment.telegram_file_id
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            collected.append(
                (file_id, _photo_caption_for(message), message.sender_name or "", message)
            )

    # RAG context first (meaning match), then the recent session (recency).
    for block in ctx.context_blocks:
        for message in block.messages:
            _add(message)
    for message in ctx.recent:
        _add(message)

    candidates: list[PhotoCandidate] = []
    for index, (file_id, caption, sender, message) in enumerate(collected, start=1):
        if len(candidates) >= settings.vision_photo_candidates:
            break
        candidates.append(
            PhotoCandidate(
                index=index,
                telegram_file_id=file_id,
                caption=caption,
                sender_name=sender or None,
                created_at=getattr(message, "created_at", None),
            )
        )
    return candidates


class ComposeStage:
    def __init__(self, llm: LLMProviderProtocol) -> None:
        self._llm = llm

    async def run(self, ctx: TurnPipelineContext) -> bool:
        llm_started = time.perf_counter()
        session_messages = session_context_messages(ctx.recent)
        metrics_block = None
        if ctx.sender_profile is not None and ctx.sender_metrics is not None:
            metrics_block = render_feedback_block(
                name=ctx.sender_profile.display_name,
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
                name=ctx.sender_profile.display_name,
                annoyance=ctx.annoyance,
            )
        # Vision: attach the current + recent-session images when enabled; the
        # provider routes the call to the vision model only when images are present.
        images = _collect_turn_images(ctx) if settings.vision_enabled else []
        # Photo album: photos the bot could re-send, matched to the context by
        # RAG "по смыслу" + the recent session.
        photo_candidates = _collect_photo_candidates(ctx) if settings.vision_enabled else []
        ctx.reply = await self._llm.generate(
            user_message=ctx.turn.message,
            context_blocks=ctx.context_blocks,
            session_messages=session_messages,
            humor_quotes=ctx.humor_quotes or None,
            knowledge_blocks=ctx.knowledge_blocks or None,
            meme_blocks=ctx.meme_blocks or None,
            meme_menu=ctx.meme_menu or None,
            metrics_block=metrics_block,
            attitude_note=attitude_note,
            sender_telegram_id=ctx.turn.sender_telegram_id,
            sender_name=ctx.sender_name,
            tone=ctx.turn_plan.tone,
            needs_clarification=ctx.turn_plan.needs_clarification,
            clarification_hint=ctx.turn_plan.clarification_hint,
            uses_pro_model=ctx.turn_plan.uses_pro_model,
            reply_to_text=ctx.turn.reply_to_text,
            reply_to_sender_telegram_id=ctx.turn.reply_to_sender_telegram_id,
            reply_to_sender_name=ctx.turn.reply_to_sender_name,
            images=images or None,
            photo_candidates=photo_candidates or None,
        )
        # Resolve the [photo:<index>] marker the model may have emitted: strip it
        # from the reply and remember the file_id the bot should re-send.
        clean_reply, photo_index = extract_photo_index(ctx.reply)
        if photo_index is not None:
            if 1 <= photo_index <= len(photo_candidates):
                ctx.photo_file_id = photo_candidates[photo_index - 1].telegram_file_id
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
        ctx.llm_ms = (time.perf_counter() - llm_started) * 1000
        logger.info(
            "turn_stage llm request_id=%s reply_len=%s llm_ms=%.1f",
            get_request_id(),
            len(ctx.reply),
            ctx.llm_ms,
        )
        return True


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
        )
        self._metrics.record_turn(
            action=ctx.result.action,
            reason=ctx.result.reason,
            planner_skipped=ctx.planner_skipped,
            deep_search=ctx.turn_plan.deep_search,
        )
        return True
