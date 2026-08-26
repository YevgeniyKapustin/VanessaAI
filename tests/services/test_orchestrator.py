import pytest
from unittest.mock import AsyncMock

from app.core.messages import ContextBlock, ContextMessage, StoredMessage
from app.core.turn import ChatTurnInput
from app.decision import IntentDetector, NoiseFilter, TriggerKeywordChecker
from app.knowledge.schema import KnowledgeBlock
from app.decision.gate.user_ignore import ChatIgnoreRegistry
from app.decision.models import DecisionAction, DecisionReason, DecisionResult
from app.llm.humor.critic import CriticStatus, CriticVerdict
from app.llm.planner.turn_planner import TurnPlan
from app.rag.query_rewriter import QueryRewriter
from app.services.orchestrator.conversation_orchestrator import ConversationOrchestrator
from app.services.humor_pipeline import HumorPipeline
from app.services.orchestrator.orchestrator_config import OrchestratorConfig
from app.services.pipeline.critique_stage import CritiqueStage
from app.services.pipeline.stages import (
    ComposeStage,
    FinalizeStage,
    GateStage,
    RetrieveStage,
)
from app.services.turn_metrics import TurnMetrics


class FakeMessageRepo:
    def __init__(self) -> None:
        self._messages: dict[int, StoredMessage] = {}
        self._next_id = 1

    async def create(
        self,
        role: str,
        content: str,
        sender_telegram_id: int | None = None,
        qdrant_point_id: str | None = None,
        created_at=None,
        telegram_message_id: int | None = None,
    ) -> StoredMessage:
        message = StoredMessage(
            id=self._next_id,
            role=role,
            content=content,
            sender_telegram_id=sender_telegram_id,
            qdrant_point_id=qdrant_point_id,
            telegram_message_id=telegram_message_id,
        )
        self._messages[message.id] = message
        self._next_id += 1
        return message

    async def get_recent(self, limit: int = 50) -> list[StoredMessage]:
        return list(self._messages.values())[-limit:]

    async def fulltext_search(self, query: str, limit: int = 30) -> list[StoredMessage]:
        return []

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]:
        return [self._messages[mid] for mid in message_ids if mid in self._messages]

    async def get_existing_telegram_message_ids(
        self,
        telegram_message_ids: list[int],
    ) -> set[int]:
        return set()

    async def update_qdrant_point_id(self, message_id: int, point_id: str) -> None:
        message = self._messages[message_id]
        self._messages[message_id] = StoredMessage(
            id=message.id,
            role=message.role,
            content=message.content,
            sender_telegram_id=message.sender_telegram_id,
            qdrant_point_id=point_id,
            telegram_message_id=message.telegram_message_id,
        )


class FakeUser:
    nickname: str | None = "Тест"
    first_name: str | None = None
    username: str | None = None


class FakeUserRepo:
    async def get_or_create(self, **kwargs) -> FakeUser:
        return FakeUser()


class FakeTurnQuery:
    async def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeContextRetriever:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        query_vector: list[float] | None = None,
        skip_fts: bool = False,
        anchor_max: int | None = None,
        fts_query: str | None = None,
        semantic_queries: list[str] | None = None,
        window_before: int | None = None,
        window_after: int | None = None,
    ) -> list[ContextBlock]:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "anchor_max": anchor_max,
                "fts_query": fts_query,
                "semantic_queries": semantic_queries,
                "window_before": window_before,
                "window_after": window_after,
            }
        )
        if anchor_max is not None:
            return [
                ContextBlock(
                    anchor_id=100,
                    messages=(
                        ContextMessage(
                            id=100,
                            role="user",
                            content="найди работу",
                            is_anchor=True,
                        ),
                    ),
                )
            ]
        return [
            ContextBlock(
                anchor_id=99,
                messages=(
                    ContextMessage(id=99, role="user", content="context"),
                ),
            )
        ]


class FakeIndexing:
    def __init__(self) -> None:
        self.scheduled: list[StoredMessage] = []

    async def index_now(self, record: StoredMessage) -> None:
        self.scheduled.append(record)

    def schedule(self, record: StoredMessage) -> None:
        self.scheduled.append(record)


class FakeLLM:
    def __init__(self) -> None:
        self.last_humor_quotes: list[str] | None = None
        self.last_knowledge_blocks: list[KnowledgeBlock] | None = None
        self.last_critic_feedback: str | None = None

    async def generate(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
        critic_feedback: str | None = None,
    ) -> str:
        self.last_humor_quotes = humor_quotes
        self.last_knowledge_blocks = knowledge_blocks
        self.last_sender_name = sender_name
        self.last_critic_feedback = critic_feedback
        return f"echo: {user_message}"


class FakeCritic:
    def __init__(self, verdict: CriticVerdict | None = None) -> None:
        self._verdict = verdict or CriticVerdict(
            status=CriticStatus.APPROVED,
            score=5,
            reason="ок",
        )
        self.reviews: list[str] = []

    async def review(
        self,
        draft: str,
        *,
        user_message: str,
        humor_quotes: list[str],
    ) -> CriticVerdict:
        self.reviews.append(draft)
        return self._verdict


class FakeDecisionEngine:
    def __init__(self, action: DecisionAction) -> None:
        self._action = action
        self.recorded_chats: list[int] = []

    async def decide(
        self,
        text: str,
        telegram_chat_id: int,
        recent_messages: list[ContextMessage],
        query_vector: list[float] | None = None,
        search_text: str | None = None,
        *,
        should_reply: bool | None = None,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
        sender_telegram_id: int = 0,
        humor_ok: bool = False,
    ) -> DecisionResult:
        return DecisionResult(
            action=self._action,
            reason=(
                DecisionReason.INTENT
                if self._action == DecisionAction.REPLY
                else DecisionReason.IGNORE
            ),
        )

    def record_reply(self, telegram_chat_id: int) -> None:
        self.recorded_chats.append(telegram_chat_id)


def _build_orchestrator(
    *,
    messages: FakeMessageRepo,
    indexing: FakeIndexing,
    decision: FakeDecisionEngine,
    retriever: FakeContextRetriever | None = None,
    llm: FakeLLM | None = None,
    critic: FakeCritic | None = None,
    query_rewriter: QueryRewriter | None = None,
    defer_index_on_ignore: bool = True,
    critic_enabled: bool = False,
) -> ConversationOrchestrator:
    retriever = retriever or FakeContextRetriever()
    llm = llm or FakeLLM()
    metrics = TurnMetrics()
    config = OrchestratorConfig(
        session_window_size=10,
        session_idle_seconds=300.0,
        post_reply_listen_count=5,
        planner_prefilter_enabled=False,
        defer_index_on_ignore=defer_index_on_ignore,
        critic_enabled=critic_enabled,
    )
    humor = HumorPipeline(retriever, FakeTurnQuery(), config)
    registry = ChatIgnoreRegistry()
    gate = GateStage(
        query_rewriter or QueryRewriter(use_llm=False),
        decision,
        None,
        config,
        metrics,
        messages,
        indexing,
        registry,
    )
    return ConversationOrchestrator(
        messages=messages,
        users=FakeUserRepo(),
        config=config,
        gate=gate,
        retrieve=RetrieveStage(retriever, humor, None),
        compose=ComposeStage(llm),
        critique=CritiqueStage(llm, critic or FakeCritic(), config),
        finalize=FinalizeStage(messages, indexing, decision, config, metrics),
    )


@pytest.mark.asyncio
async def test_orchestrator_replies_and_indexes_both_messages():
    messages = FakeMessageRepo()
    indexing = FakeIndexing()
    decision = FakeDecisionEngine(DecisionAction.REPLY)
    orchestrator = _build_orchestrator(
        messages=messages,
        indexing=indexing,
        decision=decision,
        defer_index_on_ignore=False,
    )

    result = await orchestrator.handle_incoming(
        ChatTurnInput(
            telegram_chat_id=-1001,
            message="Vanessa, привет",
            sender_telegram_id=42,
        )
    )

    assert result.action == DecisionAction.REPLY
    assert result.reply == "echo: Vanessa, привет"
    assert result.context_count == 1
    assert len(messages._messages) == 2
    assert len(indexing.scheduled) == 1
    assert decision.recorded_chats == [-1001]


@pytest.mark.asyncio
async def test_orchestrator_ignores_without_reply():
    messages = FakeMessageRepo()
    indexing = FakeIndexing()
    orchestrator = _build_orchestrator(
        messages=messages,
        indexing=indexing,
        decision=FakeDecisionEngine(DecisionAction.IGNORE),
    )

    result = await orchestrator.handle_incoming(
        ChatTurnInput(
            telegram_chat_id=-1001,
            message="ок",
            sender_telegram_id=42,
        )
    )

    assert result.action == DecisionAction.IGNORE
    assert result.reply is None
    assert len(messages._messages) == 1
    assert len(indexing.scheduled) == 1


@pytest.mark.asyncio
async def test_orchestrator_runs_humor_rag_when_planner_requests_it():
    messages = FakeMessageRepo()
    indexing = FakeIndexing()
    retriever = FakeContextRetriever()
    llm = FakeLLM()
    planner = QueryRewriter(use_llm=False)
    planner.prepare = AsyncMock(
        return_value=TurnPlan(
            original="ну ладно поработаю",
            text="работа",
            skip_search=False,
            humor_ok=True,
            humor_query="личь работа",
        ),
    )
    orchestrator = _build_orchestrator(
        messages=messages,
        indexing=indexing,
        decision=FakeDecisionEngine(DecisionAction.REPLY),
        retriever=retriever,
        llm=llm,
        query_rewriter=planner,
        defer_index_on_ignore=False,
    )

    result = await orchestrator.handle_incoming(
        ChatTurnInput(
            telegram_chat_id=-1001,
            message="ну ладно поработаю",
            sender_telegram_id=42,
        )
    )

    assert result.reply == "echo: ну ладно поработаю"
    assert len(retriever.calls) == 2
    assert retriever.calls[1]["query"] == "личь работа"
    assert llm.last_humor_quotes == ["найди работу"]


@pytest.mark.asyncio
async def test_orchestrator_runs_critique_on_humor_turn_when_enabled():
    messages = FakeMessageRepo()
    indexing = FakeIndexing()
    retriever = FakeContextRetriever()
    llm = FakeLLM()
    critic = FakeCritic()
    planner = QueryRewriter(use_llm=False)
    planner.prepare = AsyncMock(
        return_value=TurnPlan(
            original="ну ладно поработаю",
            text="работа",
            skip_search=False,
            humor_ok=True,
            humor_query="личь работа",
        ),
    )
    orchestrator = _build_orchestrator(
        messages=messages,
        indexing=indexing,
        decision=FakeDecisionEngine(DecisionAction.REPLY),
        retriever=retriever,
        llm=llm,
        critic=critic,
        query_rewriter=planner,
        defer_index_on_ignore=False,
        critic_enabled=True,
    )

    result = await orchestrator.handle_incoming(
        ChatTurnInput(
            telegram_chat_id=-1001,
            message="ну ладно поработаю",
            sender_telegram_id=42,
        )
    )

    assert result.reply == "echo: ну ладно поработаю"
    assert critic.reviews == ["echo: ну ладно поработаю"]
    assert llm.last_critic_feedback is None
