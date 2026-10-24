"""Gate step for messages from other AI bots (Bot-to-Bot Communication Mode).

With the mode on, Vanessa sees every bot message in her groups. The message
is already saved as context by ingress. This step stops it before the
reaction gate and the planner unless the bot talks to Vanessa: it mentions
her, replies to her, or answers inside her listen window after she last
answered that same bot. A bot that talks to her is still held to the
``BotPeerBudget`` loop limits.
"""

import logging

from vanessa.core.session.channel_keys import dialogue_session_key, turn_channel
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.decision.bot_peer_budget import BotPeerBudget
from vanessa.pipeline.decision.gate.addressing.continuation import (
    last_bot_reply_partner_sender_id,
)
from vanessa.pipeline.decision.models import DecisionReason
from vanessa.pipeline.gate_support import finish_ignore_turn
from vanessa.pipeline.stages.gate_decision import pipeline_in_listen_window

logger = logging.getLogger("vanessa.pipeline.stages")

# Hermes queues a late follow-up message: it counts as a second reply.
_HERMES_FOLLOW_UP_COUNT = 2


def bot_peer_chat_key(ctx: TurnPipelineContext) -> str:
    return dialogue_session_key(
        channel=turn_channel(ctx.turn),
        telegram_chat_id=ctx.turn.telegram_chat_id,
    )


def bot_talks_to_vanessa(ctx: TurnPipelineContext) -> bool:
    turn = ctx.turn
    if turn.mentions_bot or turn.reply_to_bot:
        return True
    if not pipeline_in_listen_window(ctx):
        return False
    partner = last_bot_reply_partner_sender_id(ctx.recent)
    return partner is not None and partner == turn.sender_telegram_id


def record_bot_peer_reply(budget: BotPeerBudget, ctx: TurnPipelineContext) -> None:
    """Count a sent reply to a bot sender (Hermes follow-up counts too)."""
    if not ctx.turn.sender_is_bot or ctx.turn.sender_telegram_id is None:
        return
    count = _HERMES_FOLLOW_UP_COUNT if ctx.hermes_status == "asked" else 1
    budget.record_reply(
        bot_peer_chat_key(ctx), ctx.turn.sender_telegram_id, count=count
    )


class _GateBotPeerMixin:
    async def _bot_peer_should_stop(self, ctx: TurnPipelineContext) -> bool:
        key = bot_peer_chat_key(ctx)
        if not ctx.turn.sender_is_bot:
            self._bot_budget.note_human(key)
            return False
        if not bot_talks_to_vanessa(ctx):
            return await self._stop_bot_turn(ctx, DecisionReason.BOT_PEER_SIDE)
        blocked = self._bot_budget.blocked_reason(
            key, ctx.turn.sender_telegram_id or 0
        )
        if blocked is None:
            return False
        logger.info("bot_peer_budget chat=%s blocked=%s", key, blocked)
        return await self._stop_bot_turn(ctx, DecisionReason.BOT_PEER_LIMIT)

    async def _stop_bot_turn(
        self, ctx: TurnPipelineContext, reason: DecisionReason
    ) -> bool:
        ctx.planner_skipped = True
        await finish_ignore_turn(
            ctx,
            reason=reason.value,
            metrics=self._metrics,
            planner_skipped=True,
            log_event="turn_stage bot_peer",
        )
        return True
