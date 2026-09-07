from vanessa.core.generate_request import GenerateRequest, as_generate_request
from vanessa.core.protocols.compose import (
    IncomingTurnHandlerProtocol,
    LLMChatCompleter,
    LLMProviderProtocol,
    PhotoCaptionerProtocol,
    SceneDescriberProtocol,
    TurnMetricsProtocol,
)
from vanessa.core.protocols.search import (
    ContextRetrieverProtocol,
    EmbeddingProviderProtocol,
    KnowledgeVectorHit,
    KnowledgeVectorStoreProtocol,
    TurnQueryProtocol,
    VectorSearchHit,
    VectorStoreProtocol,
)
from vanessa.core.protocols.speech import SpeechAudio, SpeechSynthesizer
from vanessa.core.protocols.storage import (
    ChatUserProtocol,
    MessageIndexerProtocol,
    MessageIndexingSchedulerProtocol,
    MessageRepositoryProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
)

__all__ = [
    "ChatUserProtocol",
    "ContextRetrieverProtocol",
    "EmbeddingProviderProtocol",
    "GenerateRequest",
    "IncomingTurnHandlerProtocol",
    "KnowledgeVectorHit",
    "KnowledgeVectorStoreProtocol",
    "LLMChatCompleter",
    "LLMProviderProtocol",
    "MessageIndexerProtocol",
    "MessageIndexingSchedulerProtocol",
    "MessageRepositoryProtocol",
    "PhotoCaptionerProtocol",
    "SceneDescriberProtocol",
    "SpeechAudio",
    "SpeechSynthesizer",
    "TurnMetricsProtocol",
    "TurnQueryProtocol",
    "UnitOfWorkProtocol",
    "UserRepositoryProtocol",
    "VectorSearchHit",
    "VectorStoreProtocol",
    "as_generate_request",
]
