from vanessa.contracts.messages import TurnReply, TurnRequest, TurnStarted
from vanessa.core.turn import ConversationTurnResult


class ReplyPublisher:
    def __init__(self, broker) -> None:
        self._broker = broker

    async def started(self, request: TurnRequest) -> None:
        if not request.reply_to:
            return
        await self._broker.publish(
            request.reply_to,
            TurnStarted(
                correlation_id=request.correlation_id,
                trace_id=request.trace_id,
            ),
        )

    async def reply(
        self,
        request: TurnRequest,
        result: ConversationTurnResult,
    ) -> None:
        if not request.reply_to:
            return
        await self._broker.publish(
            request.reply_to,
            TurnReply(
                correlation_id=request.correlation_id,
                trace_id=request.trace_id,
                action=result.action,
                reason=result.reason,
                reply=result.reply,
                messages=result.messages,
                context_count=result.context_count,
                relevance_score=result.relevance_score,
                sticker_tag=result.sticker_tag,
                photo_file_id=result.photo_file_id,
                photo_data_url=result.photo_data_url,
            ),
        )
