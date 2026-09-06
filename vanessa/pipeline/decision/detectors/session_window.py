from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.gate.expectation.reply_expectation import (
    is_dismissal_request,
)
from vanessa.pipeline.decision.protocols import (
    IntentDetectorProtocol,
    TriggerCheckerProtocol,
)


def _last_dismissal_index(window: list[ContextMessage]) -> int:
    last = -1
    for index, message in enumerate(window):
        if message.role == "user" and is_dismissal_request(message.content):
            last = index
    return last


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
        last_dismissal_idx = _last_dismissal_index(window)
        return self._window_has_active_request(window, last_dismissal_idx)

    def _window_has_active_request(
        self,
        window: list[ContextMessage],
        last_dismissal_idx: int,
    ) -> bool:
        for index, message in enumerate(window):
            if self._message_is_active_request(
                index,
                message,
                last_dismissal_idx,
            ):
                return True
        return False

    def _message_is_active_request(
        self,
        index: int,
        message: ContextMessage,
        last_dismissal_idx: int,
    ) -> bool:
        if message.role != "user":
            return False
        if last_dismissal_idx >= 0 and index <= last_dismissal_idx:
            return False
        return self._is_active_request(
            message.content,
            after_dismissal=last_dismissal_idx >= 0,
        )

    def _is_active_request(self, content: str, *, after_dismissal: bool) -> bool:
        intent = self._intent.detect(content)
        trigger = self._triggers.detect(content)
        if after_dismissal:
            return intent.mentions_bot and (intent.detected or trigger.detected)
        return intent.detected or trigger.detected
