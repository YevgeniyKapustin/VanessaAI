from fastapi import APIRouter, Depends

from app.api.auth import verify_internal_token
from app.api.deps import get_incoming_turn_handler
from app.api.schemas.chat import ChatRequest, ChatResponse
from app.core.protocols import IncomingTurnHandlerProtocol
from app.core.turn import ChatTurnInput

router = APIRouter(dependencies=[Depends(verify_internal_token)])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    handler: IncomingTurnHandlerProtocol = Depends(get_incoming_turn_handler),
) -> ChatResponse:
    result = await handler.handle_incoming(
        ChatTurnInput(
            telegram_chat_id=body.telegram_chat_id,
            message=body.message,
            sender_telegram_id=body.sender_telegram_id,
            chat_title=body.chat_title,
            chat_type=body.chat_type,
            sender_username=body.sender_username,
            sender_first_name=body.sender_first_name,
            sender_last_name=body.sender_last_name,
            mentions_bot=body.mentions_bot,
            reply_to_bot=body.reply_to_bot,
        )
    )
    return ChatResponse(
        action=result.action,
        reason=result.reason,
        reply=result.reply,
        context_count=result.context_count,
        relevance_score=result.relevance_score,
    )
