from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.gate.addressing.compose_gate import ComposeGatePolicy
from vanessa.pipeline.decision.gate.eligibility.reply_eligibility import (
    ReplyEligibility,
)
from vanessa.pipeline.decision.gate.eligibility.user_ignore import ChatIgnoreRegistry
from vanessa.pipeline.decision.gate.protocols import ReplyEligibilityProtocol
from vanessa.pipeline.decision.models import DecisionReason, DecisionResult
from vanessa.pipeline.decision.protocols import (
    IntentDetectorProtocol,
    NoiseFilterProtocol,
    TriggerCheckerProtocol,
)
from vanessa.pipeline.decision.rule_outcomes import _ignore


def resolve_eligibility_gate(
    intent_detector: IntentDetectorProtocol,
    trigger_checker: TriggerCheckerProtocol,
    noise_filter: NoiseFilterProtocol,
    *,
    reply_eligibility: ReplyEligibilityProtocol | None,
    ignore_registry: ChatIgnoreRegistry | None,
    compose_gate: ComposeGatePolicy | None,
) -> tuple[ReplyEligibilityProtocol, ComposeGatePolicy]:
    registry = ignore_registry or ChatIgnoreRegistry()
    eligibility = reply_eligibility or ReplyEligibility(
        intent_detector,
        trigger_checker,
        noise_filter,
        registry,
    )
    gate = compose_gate or ComposeGatePolicy(eligibility)
    return eligibility, gate


def apply_compose_gate(
    compose_gate: ComposeGatePolicy,
    result: DecisionResult,
    context: DecisionContext,
    *,
    humor_ok: bool,
) -> DecisionResult:
    if not compose_gate.should_downgrade_to_ignore(
        result,
        context,
        humor_ok=humor_ok,
    ):
        return result
    return _ignore(context, DecisionReason.NOT_EXPECTED)
