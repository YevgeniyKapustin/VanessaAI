from dataclasses import dataclass, field
import time

from app.config.content import MemeDefContent
from app.core.session.chat_session_state import ChatSessionState
from app.core.messages import ContextBlock, ContextMessage, StoredMessage
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionResult
from app.knowledge.metrics.retriever import SenderProfile
from app.knowledge.metrics.schema import PersonMetrics
from app.knowledge.schema import KnowledgeBlock
from app.llm.humor.critic import CriticVerdict
from app.llm.planner.turn_planner import TurnPlan


@dataclass
class TurnPipelineContext:
    turn: ChatTurnInput
    started: float = field(default_factory=time.perf_counter)
    user_msg: StoredMessage | None = None
    sender_name: str = ""
    session: ChatSessionState | None = None
    recent: list[ContextMessage] = field(default_factory=list)
    planner_skipped: bool = False
    turn_plan: TurnPlan | None = None
    decision: DecisionResult | None = None
    context_blocks: list[ContextBlock] = field(default_factory=list)
    humor_quotes: list[str] = field(default_factory=list)
    knowledge_blocks: list[KnowledgeBlock] = field(default_factory=list)
    meme_blocks: list[MemeDefContent] = field(default_factory=list)
    meme_menu: list[MemeDefContent] = field(default_factory=list)
    sender_profile: SenderProfile | None = None
    reply: str | None = None
    result: ConversationTurnResult | None = None
    critic_verdict: CriticVerdict | None = None
    critic_iterations: int = 0
    critic_ms: float = 0.0
    plan_ms: float = 0.0
    decision_ms: float = 0.0
    rag_ms: float = 0.0
    semantic_ms: float = 0.0
    humor_rag_ms: float = 0.0
    llm_ms: float = 0.0
    embed_ms: float = 0.0

    @property
    def context_count(self) -> int:
        return sum(len(block.messages) for block in self.context_blocks)

    @property
    def sender_metrics(self) -> PersonMetrics | None:
        return self.sender_profile.metrics if self.sender_profile else None
