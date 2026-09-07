from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.detectors.intent import IntentResult
from vanessa.pipeline.decision.rules import DirectAddressRule


def test_telegram_addressing_requires_mention_entity() -> None:
    context = DecisionContext(
        text="привет",
        addressing="telegram",
        mentions_bot=False,
        intent=IntentResult(detected=True, mentions_bot=True),
    )
    assert context.telegram_addressed_with_expectation is False
    assert DirectAddressRule().evaluate(context) is None


def test_addressed_mode_does_not_require_telegram_mention_entity() -> None:
    context = DecisionContext(
        text="Ванесса, привет",
        addressing="addressed",
        mentions_bot=False,
        intent=IntentResult(detected=True, mentions_bot=True),
    )
    assert context.telegram_addressed_with_expectation is True
    result = DirectAddressRule().evaluate(context)
    assert result is not None
    assert result.reason.value == "addressing"


def test_addressed_mode_still_ignores_undirected_small_talk() -> None:
    context = DecisionContext(
        text="привет",
        addressing="addressed",
        mentions_bot=False,
        intent=IntentResult(detected=False, mentions_bot=False),
    )
    assert context.telegram_addressed_with_expectation is False
    assert DirectAddressRule().evaluate(context) is None
