from vanessa.core.generate_request import GenerateRequest, as_generate_request
from vanessa.core.protocols.compose import (
    IncomingTurnHandlerProtocol,
    LLMChatCompleter,
    LLMProviderProtocol,
    PhotoCaptionerProtocol,
    SceneDescriberProtocol,
    TurnMetricsProtocol,
)
from vanessa.core.protocols.hermes import HermesHealthProtocol
from vanessa.core.protocols.reminders import ReminderStoreProtocol
from vanessa.core.protocols.speech import SpeechAudio, SpeechSynthesizer
from vanessa.core.protocols.storage import (
    ChatUserProtocol,
    MessageRepositoryProtocol,
    UnitOfWorkProtocol,
    UserRepositoryProtocol,
)

__all__ = [
    "ChatUserProtocol",
    "GenerateRequest",
    "HermesHealthProtocol",
    "IncomingTurnHandlerProtocol",
    "LLMChatCompleter",
    "LLMProviderProtocol",
    "MessageRepositoryProtocol",
    "PhotoCaptionerProtocol",
    "ReminderStoreProtocol",
    "SceneDescriberProtocol",
    "SpeechAudio",
    "SpeechSynthesizer",
    "TurnMetricsProtocol",
    "UnitOfWorkProtocol",
    "UserRepositoryProtocol",
    "as_generate_request",
]
