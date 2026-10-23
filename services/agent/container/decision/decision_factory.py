from services.agent.container.graph import ProcessGraph
from vanessa.pipeline.decision import DecisionEngine
from vanessa.pipeline.decision.protocols import DecisionEngineProtocol


class DecisionFactory:
    def __init__(self, graph: ProcessGraph) -> None:
        self._graph = graph

    def engine(self) -> DecisionEngineProtocol:
        decision = self._graph.decision
        signals = decision.signals
        eligibility = decision.eligibility
        return DecisionEngine(
            intent_detector=signals.intent,
            trigger_checker=signals.triggers,
            session_analyzer=eligibility.session,
            rate_limiter=decision.rate_limiter,
            noise_filter=signals.noise,
            reply_eligibility=eligibility.reply,
            block_consecutive_replies=eligibility.block_consecutive_replies,
            ignore_registry=decision.ignore_registry,
        )
