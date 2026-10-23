"""Is the turn a direct request to Vanessa: a mention, a reply, or her name?"""

from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.detectors.intent import IntentDetector


def is_direct_request(ctx: TurnPipelineContext) -> bool:
    turn = ctx.turn
    if turn.mentions_bot or turn.reply_to_bot:
        return True
    return IntentDetector().detect(turn.message).mentions_bot
