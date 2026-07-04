from dataclasses import dataclass, field
import time

from app.core.session.chat_session_state import ChatSessionState
from app.core.messages import ContextBlock, ContextMessage, StoredMessage
from app.core.turn import ChatTurnInput, ConversationTurnResult
from app.decision.models import DecisionResult
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
    reply: str | None = None
    result: ConversationTurnResult | None = None
    plan_ms: float = 0.0
    decision_ms: float = 0.0
    rag_ms: float = 0.0
    humor_rag_ms: float = 0.0
    llm_ms: float = 0.0
    embed_ms: float = 0.0

    @property
    def context_count(self) -> int:
        return sum(len(block.messages) for block in self.context_blocks)
