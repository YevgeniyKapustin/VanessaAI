from app.core.messages import ContextMessage
from app.decision.protocols import IntentDetectorProtocol, TriggerCheckerProtocol


class SessionWindowAnalyzer:
    def __init__(
        self,
        window_size: int,
        intent_detector: IntentDetectorProtocol,
        trigger_checker: TriggerCheckerProtocol,
    ) -> None:
        self._window_size = window_size
        self._intent = intent_detector
        self._triggers = trigger_checker

    def has_active_request(self, messages: list[ContextMessage]) -> bool:
        window = messages[-self._window_size :]
        for message in window:
            if message.role != "user":
                continue
            if self._intent.detect(message.content).detected:
                return True
            if self._triggers.detect(message.content).detected:
                return True
        return False
