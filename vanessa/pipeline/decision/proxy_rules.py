"""Decision rules for proxy mode and the owner's private chat.

Both cases are explicit: the owner already decided that Vanessa may speak
for him in the agents' chat, and a DM to her is addressed to her by design.
The usual addressing rules cannot see that, so these rules accept the turn
before the noise and listen-window checks.
"""

from vanessa.pipeline.decision.context import DecisionContext
from vanessa.pipeline.decision.models import DecisionReason, DecisionResult
from vanessa.pipeline.decision.rule_outcomes import _reply


class OwnerDmRule:
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.owner_dm or not context.sender_is_owner:
            return None
        return _reply(context, DecisionReason.OWNER_DM)


class ProxyQuestionRule:
    def evaluate(self, context: DecisionContext) -> DecisionResult | None:
        if not context.proxy_question:
            return None
        return _reply(context, DecisionReason.PROXY_QUESTION)
