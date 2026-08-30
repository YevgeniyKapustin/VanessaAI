import time
from dataclasses import dataclass, field

from vanessa.config.content import MemeDefContent
from vanessa.core.messages import ContextBlock, ContextMessage, StoredMessage, WebResult
from vanessa.core.session.chat_session_state import ChatSessionState
from vanessa.core.turn import ChatTurnInput, ConversationTurnResult
from vanessa.knowledge.metrics.retriever import SenderProfile
from vanessa.knowledge.metrics.schema import PersonMetrics
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.decision.models import DecisionResult
from vanessa.pipeline.decision.turn_plan import TurnPlan


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
    # Live web search results (the "googling" skill), fetched by the Retrieve
    # stage when the planner flagged the turn and injected into the compose
    # prompt as a "live web results" block.
    web_blocks: list[WebResult] = field(default_factory=list)
    meme_blocks: list[MemeDefContent] = field(default_factory=list)
    meme_menu: list[MemeDefContent] = field(default_factory=list)
    sender_profile: SenderProfile | None = None
    # Loop-repetition signal from the gate: how deep the same-topic loop is and
    # how annoyed Vanessa is (drives LowAttitudeRule + the cold compose note).
    loop_strength: int = 0
    annoyance: float = 0.0
    reply: str | None = None
    # When the compose stage decides to refuse the answer (repeated same-sender
    # message / spam, or the model returned an empty "stay silent" reply), the
    # orchestrator finalizes the turn as an IGNORE via ``FinalizeStage.skip``
    # with this reason instead of sending a reply.
    refuse_reason: str | None = None
    # When the compose model picks a photo from the album, the resolved Telegram
    # file_id of the photo to re-send (via the [photo:<index>] marker).
    photo_file_id: str | None = None
    # Base64 data URL of the same photo (the stored bytes) — lets the bot fall
    # back to an upload when the Telegram file_id is stale at delivery time.
    photo_data_url: str | None = None
    result: ConversationTurnResult | None = None
    plan_ms: float = 0.0
    decision_ms: float = 0.0
    # Latency of the lightweight pre-planner Decision Gate (reaction classifier).
    reaction_gate_ms: float = 0.0
    rag_ms: float = 0.0
    semantic_ms: float = 0.0
    # Live web-search latency (only set when the turn was flagged for search).
    web_ms: float = 0.0
    humor_rag_ms: float = 0.0
    llm_ms: float = 0.0
    embed_ms: float = 0.0

    @property
    def context_count(self) -> int:
        return sum(len(block.messages) for block in self.context_blocks)

    @property
    def sender_metrics(self) -> PersonMetrics | None:
        return self.sender_profile.metrics if self.sender_profile else None
