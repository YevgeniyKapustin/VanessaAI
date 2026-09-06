from __future__ import annotations

from vanessa.config.content import get_bot_name_aliases, get_trigger_keywords
from vanessa.pipeline.decision import (
    IntentDetector,
    NoiseFilter,
    TriggerKeywordChecker,
)


class MentionSignals:
    def __init__(
        self,
        intent: IntentDetector | None = None,
        triggers: TriggerKeywordChecker | None = None,
        noise: NoiseFilter | None = None,
    ) -> None:
        self.intent = intent or IntentDetector(bot_names=get_bot_name_aliases())
        self.triggers = triggers or TriggerKeywordChecker(
            keywords=get_trigger_keywords(),
        )
        self.noise = noise or NoiseFilter()
