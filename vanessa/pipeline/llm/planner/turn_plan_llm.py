from __future__ import annotations

import logging

from vanessa.config.conversation_config import load_conversation_config
from vanessa.core.messages import ContextMessage
from vanessa.infrastructure.observability.trace_log import trace_event
from vanessa.knowledge.users.nicknames import format_nicknames_for_planner
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.turn_plan_parse import parse_llm_response
from vanessa.pipeline.llm.prompts.session_format import (
    format_session_messages,
    session_context_messages,
)
from vanessa.pipeline.llm.providers.protocols import create_chat_completer
from vanessa.pipeline.schedule.timing import planner_now_text

logger = logging.getLogger("vanessa.pipeline.llm.planner.turn_planner")

_PARTICIPANTS_PLACEHOLDER = "(нет данных)"


def _yes_no(*, enabled: bool) -> str:
    return "yes" if enabled else "no"


class _TurnPlanLlmMixin:
    async def _plan_with_llm(
        self,
        message: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
        sender_name: str = "",
        sender_is_owner: bool = False,
    ) -> TurnPlan:
        client = self._client or create_chat_completer()
        participants = await self._participants_digest(
            message, recent_messages, sender_name
        )
        prompt = self._content.rag.planner_prompt.format(
            message=message,
            sender=sender_name.strip() or "(unknown)",
            sender_is_owner=_yes_no(enabled=sender_is_owner),
            recent_messages=self._format_recent(recent_messages) or "(none)",
            nicknames=format_nicknames_for_planner(),
            participants=participants,
            mentions_bot=_yes_no(enabled=mentions_bot),
            reply_to_bot=_yes_no(enabled=reply_to_bot),
            reply_to_other_user=_yes_no(enabled=reply_to_other_user),
            listen_window=_yes_no(enabled=in_listen_window),
            now=planner_now_text(),
        )
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="planner",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        plan = parse_llm_response(message, raw)
        trace_event("planner_plan", model=self._model, plan=plan)
        return plan

    async def _participants_digest(
        self,
        message: str,
        recent_messages: list[ContextMessage],
        sender_name: str,
    ) -> str:
        if self._participants_provider is None:
            return _PARTICIPANTS_PLACEHOLDER
        try:
            # The digest is turn-scoped: it must know the current message
            # and the recent window to render only relevant people.
            digest = (
                await self._call_participants(
                    message, recent_messages, sender_name
                )
            ).strip()
        except Exception:
            logger.exception("participants_digest_failed, using placeholder")
            return _PARTICIPANTS_PLACEHOLDER
        return digest or _PARTICIPANTS_PLACEHOLDER

    async def _call_participants(
        self,
        message: str,
        recent_messages: list[ContextMessage],
        sender_name: str,
    ) -> str:
        provider = self._participants_provider
        if provider is None:
            return ""
        try:
            return await provider(message, recent_messages, sender_name)
        except TypeError:
            return await provider(message, recent_messages)

    def _format_recent(self, recent_messages: list[ContextMessage]) -> str:
        prior = session_context_messages(recent_messages)
        limit = load_conversation_config().session_window_size
        return format_session_messages(prior[-limit:], self._content)
