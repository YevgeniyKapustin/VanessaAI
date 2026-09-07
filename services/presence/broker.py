from __future__ import annotations

import logging
from uuid import uuid4

from services.presence.models import PresenceReply, PresenceTurn
from services.presence.turn_request import try_build_turn_request
from vanessa.contracts.messages import TurnReply, TurnStarted
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)

# FIXME(slice-1a): if channel / optional telegram ids / scene_image are missing
# on TurnRequest, process() returns None instead of publishing.


class PresenceBroker:
    def __init__(
        self,
        broker,
        *,
        streams: BrokerStreams,
        timeout: float,
        presence_id: str | None = None,
    ) -> None:
        self._broker = broker
        self._streams = streams
        self._timeout = timeout
        self._presence_id = presence_id or f"presence-{uuid4().hex[:8]}"

    async def ping(self) -> None:
        await self._broker.ping()

    async def process(self, turn: PresenceTurn) -> PresenceReply | None:
        correlation_id = f"vrchat:{uuid4().hex}"
        request = try_build_turn_request(
            turn,
            correlation_id=correlation_id,
            reply_to=self._streams.reply(self._presence_id, correlation_id),
        )
        if request is None:
            logger.warning("presence_turn_not_sent_contract_pending")
            return None
        return await self.request_turn(request)

    async def request_turn(self, request) -> PresenceReply:
        reply = await self._broker.request(
            self._streams.turns,
            request,
            timeout=self._timeout,
            expect=TurnReply,
            on_message=_ignore_started,
        )
        return PresenceReply(
            action=reply.action,
            reason=reply.reason,
            text=reply.reply,
        )


async def _ignore_started(msg) -> None:
    if isinstance(msg, TurnStarted):
        return
