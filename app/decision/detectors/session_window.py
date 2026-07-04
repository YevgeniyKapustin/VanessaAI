from app.core.messages import ContextMessage
from app.decision.protocols import IntentDetectorProtocol, TriggerCheckerProtocol
from app.decision.gate.reply_expectation import is_dismissal_request


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
        last_dismissal_idx = -1
        for index, message in enumerate(window):
            if message.role == "user" and is_dismissal_request(message.content):
                last_dismissal_idx = index

        for index, message in enumerate(window):
            if message.role != "user":
                continue
            if last_dismissal_idx >= 0 and index <= last_dismissal_idx:
                continue
            intent = self._intent.detect(message.content)
            trigger = self._triggers.detect(message.content)
            if last_dismissal_idx >= 0:
                if intent.mentions_bot and (intent.detected or trigger.detected):
                    return True
                continue
            if intent.detected or trigger.detected:
                return True
        return False
