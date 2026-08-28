import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.auth import verify_internal_token
from app.api.deps import get_incoming_turn_handler
from app.api.schemas.chat import ChatRequest, ChatResponse
from app.core.protocols import IncomingTurnHandlerProtocol
from app.core.request_context import set_planning_started_signal
from app.core.turn import ChatTurnInput

router = APIRouter(dependencies=[Depends(verify_internal_token)])


def _sse(event: str, payload: object) -> str:
    """Format one Server-Sent Events frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatRequest,
    handler: IncomingTurnHandlerProtocol = Depends(get_incoming_turn_handler),
) -> StreamingResponse:
    turn = ChatTurnInput(
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
        reply_to_other_user=body.reply_to_other_user,
        reply_to_sender_telegram_id=body.reply_to_sender_telegram_id,
        reply_to_message_id=body.reply_to_message_id,
        reply_to_text=body.reply_to_text,
        reply_to_sender_name=body.reply_to_sender_name,
    )

    async def event_stream():
        started = asyncio.Event()

        async def signal_started() -> None:
            """Fired by the orchestrator once the decision gate has passed."""
            started.set()

        set_planning_started_signal(signal_started)
        wait_task: asyncio.Task | None = None
        try:
            task = asyncio.create_task(handler.handle_incoming(turn))
            wait_task = asyncio.create_task(started.wait())
            done, _ = await asyncio.wait(
                {task, wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if wait_task in done and started.is_set():
                # The gate passed and the pipeline is composing an actual
                # answer: tell the bot to show "typing..." for the rest of the
                # turn. Ignored messages never emit this event.
                yield _sse("started", {})
            result = await task
            payload = ChatResponse(
                action=result.action,
                reason=result.reason,
                reply=result.reply,
                messages=result.messages,
                context_count=result.context_count,
                relevance_score=result.relevance_score,
                sticker_tag=result.sticker_tag,
            )
            yield _sse("result", payload.model_dump())
        finally:
            set_planning_started_signal(None)
            if wait_task is not None:
                wait_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await wait_task

    return StreamingResponse(event_stream(), media_type="text/event-stream")
