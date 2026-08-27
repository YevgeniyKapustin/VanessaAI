from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.llm.format.llm_json import normalize_llm_json
from app.llm.providers.protocols import LLMChatCompleter, create_chat_completer

from app.config.content import AppContent, get_content
from app.config.conversation_config import load_conversation_config
from app.config.settings import settings
from app.llm.planner.generation_config import LLMGenerationParams
from app.core.messages import ContextMessage
from app.core.users.nicknames import format_nicknames_for_planner
from app.llm.prompts.session_format import format_session_messages, session_context_messages

logger = logging.getLogger(__name__)


_TONE_VALUES = frozenset({"neutral", "serious", "ironic", "humorous"})


def _parse_tone(value: object) -> str:
    if not isinstance(value, str):
        return "neutral"
    tone = value.strip().lower()
    return tone if tone in _TONE_VALUES else "neutral"


@dataclass(frozen=True, slots=True)
class TurnPlan:
    original: str
    text: str
    skip_search: bool
    tone: str = "neutral"
    humor_ok: bool = False
    humor_query: str = ""
    should_reply: bool | None = None
    deep_search: bool = False
    knowledge_indexes: tuple[str, ...] = ()
    knowledge_query: str = ""
    # True when the user asks a concrete fact about a person ("во что играет
    # Крабер?") -> the compose prompt injects the raw dossier; False (default)
    # injects only the compact LLM portrait as background context.
    knowledge_detail: bool = False
    needs_clarification: bool = False
    clarification_hint: str = ""
    # True when the turn needs the upscaled compose model (deepseek-v4-pro):
    # super-complex synthesis, coding, long multi-step reasoning. The gate
    # planner decides; the composer routes the generation call accordingly.
    uses_pro_model: bool = False
    # Short reason for declining a reply — filled only when should_reply=false
    # or skip=true (e.g. «пустая фраза», «общение между собой», «прощание»).
    reason: str = ""

    def to_trace_dict(self) -> dict[str, Any]:
        """Serialize the plan for the Langfuse trace (gate span output).

        Bounded, debugging-friendly projection of the planner's output. Omits
        ``original`` (the raw user message is already on the trace root) so the
        Langfuse observation panel stays readable while still showing every
        decision the planner made.
        """
        return {
            "search_query": self.text,
            "skip_search": self.skip_search,
            "should_reply": self.should_reply,
            "tone": self.tone,
            "humor_ok": self.humor_ok,
            "humor_query": self.humor_query,
            "deep_search": self.deep_search,
            "knowledge_indexes": list(self.knowledge_indexes),
            "knowledge_query": self.knowledge_query,
            "knowledge_detail": self.knowledge_detail,
            "needs_clarification": self.needs_clarification,
            "clarification_hint": self.clarification_hint,
            "uses_pro_model": self.uses_pro_model,
            "reason": self.reason,
        }


class TurnPlanner:
    def __init__(
        self,
        content: AppContent | None = None,
        *,
        use_llm: bool | None = None,
        llm_client: LLMChatCompleter | None = None,
        llm_model: str | None = None,
        generation: LLMGenerationParams | None = None,
        participants_provider: Callable[
            [str, list[ContextMessage]], Awaitable[str]
        ] | None = None,
    ) -> None:
        self._content = content or get_content()
        self._use_llm = (
            use_llm
            if use_llm is not None
            else settings.rag_query_rewrite_use_llm
        )
        self._client = llm_client
        self._model = llm_model or settings.planner_model
        self._generation = (
            generation
            or self._content.llm.generation.planner.to_params()
        )
        # Optional per-participant summaries (from the knowledge vault) that
        # help the model compose queries matching the semantic archive.
        self._participants_provider = participants_provider

    async def prepare(
        self,
        message: str,
        recent_messages: list[ContextMessage] | None = None,
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
    ) -> TurnPlan:
        if not self._use_llm:
            result = self._fallback(message)
            logger.info(
                "turn_plan source=fallback search=%r skip=%s should_reply=%s "
                "tone=%s humor_ok=%s humor_query=%r knowledge=%s knowledge_query=%r "
                "knowledge_detail=%s needs_clarification=%s reason=%r",
                result.text,
                result.skip_search,
                result.should_reply,
                result.tone,
                result.humor_ok,
                result.humor_query,
                result.knowledge_indexes,
                result.knowledge_query,
                result.knowledge_detail,
                result.needs_clarification,
                result.reason,
            )
            return result

        try:
            result = await self._plan_with_llm(
                message,
                recent_messages or [],
                mentions_bot=mentions_bot,
                reply_to_bot=reply_to_bot,
                reply_to_other_user=reply_to_other_user,
                in_listen_window=in_listen_window,
            )
        except Exception:
            logger.exception(
                "turn_plan failed original=%r, using fallback",
                message,
            )
            result = self._fallback(message)
        else:
            logger.info(
                "turn_plan source=llm search=%r skip=%s should_reply=%s "
                "tone=%s humor_ok=%s humor_query=%r deep_search=%s "
                "knowledge=%s knowledge_query=%r knowledge_detail=%s "
                "needs_clarification=%s uses_pro_model=%s reason=%r",
                result.text,
                result.skip_search,
                result.should_reply,
                result.tone,
                result.humor_ok,
                result.humor_query,
                result.deep_search,
                result.knowledge_indexes,
                result.knowledge_query,
                result.knowledge_detail,
                result.needs_clarification,
                result.uses_pro_model,
                result.reason,
            )
        return result

    async def _plan_with_llm(
        self,
        message: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
    ) -> TurnPlan:
        client = self._client or create_chat_completer()
        participants = "(нет данных)"
        if self._participants_provider is not None:
            try:
                # The digest is turn-scoped: it must know the current message
                # and the recent window to render only relevant people.
                participants = (
                    await self._participants_provider(message, recent_messages)
                ).strip() or participants
            except Exception:
                logger.exception("participants_digest_failed, using placeholder")
        prompt = self._content.rag.planner_prompt.format(
            message=message,
            recent_messages=self._format_recent(recent_messages) or "(none)",
            nicknames=format_nicknames_for_planner(),
            participants=participants,
            mentions_bot="yes" if mentions_bot else "no",
            reply_to_bot="yes" if reply_to_bot else "no",
            reply_to_other_user="yes" if reply_to_other_user else "no",
            listen_window="yes" if in_listen_window else "no",
        )
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="planner",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        return self._parse_llm_response(message, raw)

    @staticmethod
    def _normalize_llm_json(raw: str) -> str:
        return normalize_llm_json(raw)

    def _parse_llm_response(self, original: str, raw: str) -> TurnPlan:
        normalized = self._normalize_llm_json(raw)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = {"search_query": normalized, "skip": False}

        reason = str(payload.get("reason", "")).strip()

        if payload.get("skip") is True:
            return TurnPlan(
                original=original,
                text="",
                skip_search=True,
                should_reply=False,
                reason=reason,
            )

        if payload.get("needs_clarification") is True:
            # The user's message references something without context — reply with
            # a short clarifying question, not a full answer. There is nothing
            # meaningful to search for.
            clarification_hint = str(payload.get("clarification_hint", "")).strip()
            return TurnPlan(
                original=original,
                text="",
                skip_search=True,
                tone=_parse_tone(payload.get("tone")),
                should_reply=True,
                needs_clarification=True,
                clarification_hint=clarification_hint,
            )

        text = str(payload.get("search_query", "")).strip()
        tone = _parse_tone(payload.get("tone"))
        humor_ok = payload.get("humor_ok") is True
        humor_query = str(payload.get("humor_query", "")).strip()
        if humor_ok and not humor_query:
            humor_ok = False
        should_reply = _parse_should_reply(payload.get("should_reply"))
        deep_search = payload.get("deep_search") is True
        knowledge_indexes = tuple(
            str(item).strip().lower()
            for item in _as_list(payload.get("knowledge_indexes"))
            if str(item).strip()
        )
        knowledge_query = str(payload.get("knowledge_query", "")).strip()
        knowledge_detail = payload.get("knowledge_detail") is True
        uses_pro_model = payload.get("uses_pro_model") is True
        return TurnPlan(
            original=original,
            text=text,
            skip_search=not text,
            tone=tone,
            humor_ok=humor_ok,
            humor_query=humor_query if humor_ok else "",
            should_reply=should_reply,
            deep_search=deep_search,
            knowledge_indexes=knowledge_indexes,
            knowledge_query=knowledge_query,
            knowledge_detail=knowledge_detail,
            uses_pro_model=uses_pro_model,
            reason=reason,
        )

    @staticmethod
    def _fallback(message: str) -> TurnPlan:
        text = message.strip()
        return TurnPlan(
            original=message,
            text=text,
            skip_search=not text,
            should_reply=None,
        )

    def _format_recent(self, recent_messages: list[ContextMessage]) -> str:
        prior = session_context_messages(recent_messages)
        limit = load_conversation_config().session_window_size
        return format_session_messages(prior[-limit:], self._content)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _parse_should_reply(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "да", "1"}:
            return True
        if normalized in {"false", "no", "нет", "0"}:
            return False
    return None
