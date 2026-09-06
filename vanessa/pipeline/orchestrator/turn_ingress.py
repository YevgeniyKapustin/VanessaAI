import logging

from vanessa.core.messages import attachments_to_dicts
from vanessa.core.request_context import get_planning_started_signal, get_request_id
from vanessa.core.session.chat_session_state import load_chat_session_state
from vanessa.core.turn import ChatTurnInput
from vanessa.infrastructure.observability.metrics import record_user_activity
from vanessa.knowledge.users.display_names import resolve_user_display_name
from vanessa.knowledge.users.nicknames import ensure_people_alias_cache
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger(
    "vanessa.pipeline.orchestrator.conversation_orchestrator"
)


class _TurnIngressMixin:
    async def _prepare_incoming_context(
        self,
        turn: ChatTurnInput,
    ) -> TurnPipelineContext:
        ctx = TurnPipelineContext(turn=turn)
        # Track the sender and chat for the active-user / concurrent-dialog
        # gauges (DAU, sessions) — every processed message counts as activity.
        record_user_activity(turn.sender_telegram_id, turn.telegram_chat_id)

        user = await self._users.get_or_create(
            telegram_id=turn.sender_telegram_id,
            username=turn.sender_username,
            first_name=turn.sender_first_name,
            last_name=turn.sender_last_name,
        )
        await ensure_people_alias_cache()
        ctx.sender_name = resolve_user_display_name(
            turn.sender_telegram_id,
            nickname=user.nickname,
            first_name=user.first_name or turn.sender_first_name,
            username=user.username or turn.sender_username,
        )

        ctx.user_msg = await self._messages.create(
            role="user",
            content=turn.message,
            sender_telegram_id=turn.sender_telegram_id,
            reply_to_message_id=turn.reply_to_message_id,
            reply_to_text=turn.reply_to_text,
            reply_to_sender_telegram_id=turn.reply_to_sender_telegram_id,
            reply_to_sender_name=turn.reply_to_sender_name,
            # Persist vision images so a follow-up turn can reload them
            # from the session window.
            attachments=attachments_to_dicts(turn.images) or None,
        )

        ctx.session = await load_chat_session_state(
            self._messages,
            window_size=self._config.session_window_size,
            max_idle_seconds=self._config.session_idle_seconds,
            listen_max_messages=self._config.post_reply_listen_count,
        )
        ctx.recent = ctx.session.recent_messages
        return ctx

    async def _notify_planning_started(self) -> None:
        signal = get_planning_started_signal()
        if signal is None:
            return
        try:
            await signal()
        except Exception:
            logger.exception(
                "planning_started_signal_failed request_id=%s", get_request_id()
            )
