import logging

from vanessa.core.messages import attachments_to_dicts
from vanessa.core.request_context import get_planning_started_signal, get_request_id
from vanessa.core.session.channel_keys import turn_channel
from vanessa.core.session.chat_session_state import load_chat_session_state
from vanessa.core.turn import ChatTurnInput
from vanessa.infrastructure.observability.metrics import record_user_activity
from vanessa.knowledge.people.vrchat_speaker import resolve_vrchat_speaker
from vanessa.knowledge.users.display_names import (
    resolve_sender_display_name,
    resolve_user_display_name,
)
from vanessa.knowledge.users.nicknames import ensure_people_alias_cache
from vanessa.pipeline.context import TurnPipelineContext

logger = logging.getLogger(
    "vanessa.pipeline.orchestrator.conversation_orchestrator"
)


def _record_turn_activity(turn: ChatTurnInput) -> None:
    if turn.sender_telegram_id is None or turn.telegram_chat_id is None:
        return
    record_user_activity(turn.sender_telegram_id, turn.telegram_chat_id)


def _turn_display_name(turn: ChatTurnInput) -> str:
    explicit = getattr(turn, "sender_display_name", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return turn.sender_first_name or turn.sender_username or ""


def _resolve_vrchat_ingress_sender(turn: ChatTurnInput) -> str:
    """VRChat / no telegram_id: resolve a People card, never ``users.get_or_create``."""
    display = _turn_display_name(turn)
    card = resolve_vrchat_speaker(display)
    named = resolve_sender_display_name(None, display)
    if named != "user":
        return named
    return card.person_id or named


async def _resolve_ingress_sender(users, turn: ChatTurnInput) -> str:
    sender_id = turn.sender_telegram_id
    if sender_id is None:
        return _resolve_vrchat_ingress_sender(turn)
    user = await users.get_or_create(
        telegram_id=sender_id,
        username=turn.sender_username,
        first_name=turn.sender_first_name,
        last_name=turn.sender_last_name,
    )
    return resolve_user_display_name(
        sender_id,
        nickname=user.nickname,
        first_name=user.first_name or turn.sender_first_name,
        username=user.username or turn.sender_username,
    )


class _TurnIngressMixin:
    async def _prepare_incoming_context(
        self,
        turn: ChatTurnInput,
    ) -> TurnPipelineContext:
        ctx = TurnPipelineContext(turn=turn)
        _record_turn_activity(turn)
        await ensure_people_alias_cache()
        ctx.sender_name = await _resolve_ingress_sender(self._users, turn)
        channel = turn_channel(turn)
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
            channel=channel,
            sender_display_name=ctx.sender_name or None,
        )

        ctx.session = await load_chat_session_state(
            self._messages,
            window_size=self._config.session_window_size,
            max_idle_seconds=self._config.session_idle_seconds,
            listen_max_messages=self._config.post_reply_listen_count,
            channel=channel,
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
