from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from vanessa.llm.format.llm_json import normalize_llm_json
from vanessa.llm.providers.protocols import LLMChatCompleter, create_chat_completer

from vanessa.config.content import AppContent, get_content
from vanessa.config.conversation_config import load_conversation_config
from vanessa.config.settings import settings
from vanessa.llm.planner.generation_config import LLMGenerationParams
from vanessa.llm.planner.detail_detector import detect_detail_level
from vanessa.core.messages import ContextMessage
from vanessa.core.users.nicknames import format_nicknames_for_planner
from vanessa.llm.prompts.session_format import format_session_messages, session_context_messages

logger = logging.getLogger(__name__)


_TONE_VALUES = frozenset({"neutral", "serious", "ironic", "humorous"})
_DETAIL_VALUES = frozenset({"brief", "normal", "detailed"})


def _parse_tone(value: object) -> str:
    if not isinstance(value, str):
        return "neutral"
    tone = value.strip().lower()
    return tone if tone in _TONE_VALUES else "neutral"


def _parse_detail(value: object) -> str:
    if not isinstance(value, str):
        return "normal"
    detail = value.strip().lower()
    return detail if detail in _DETAIL_VALUES else "normal"


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
    # Live web search (the "googling" skill): when true, the Retrieve stage
    # runs a search API with ``web_query`` and injects the results into the
    # compose prompt as a "live web results" block. Used for fresh or external
    # facts the archive cannot hold (news, prices, current versions, unknown
    # people and things). ``web_query`` falls back to ``text`` when empty.
    web_search: bool = False
    web_query: str = ""
    needs_clarification: bool = False
    clarification_hint: str = ""
    # True when the turn needs the upscaled compose model (deepseek-v4-pro):
    # super-complex synthesis, coding, long multi-step reasoning. The gate
    # planner decides; the composer routes the generation call accordingly.
    uses_pro_model: bool = False
    # Short reason for declining a reply — filled only when should_reply=false
    # or skip=true (e.g. «пустая фраза», «общение между собой», «прощание»).
    reason: str = ""
    # Loop-repetition signal: the SAME sender keeps asking about the SAME TOPIC
    # in the recent context (different phrasings, same meaning — a loop «по
    # кругу»). ``repeated_topic`` is the boolean verdict; ``loop_level`` 0..3 is
    # how deep the loop is (1 = re-asked once, 2 = several times, 3 = stuck in a
    # constant loop). Feeds Vanessa's annoyance mechanic: a high loop level drops
    # her attitude, raises her ignore tendency and turns her replies cold.
    repeated_topic: bool = False
    loop_level: int = 0
    # Desired reply length chosen by the planner + the deterministic heuristic:
    # "brief" | "normal" | "detailed" ("normal" = the default persona voice).
    # Feeds a compose directive so Vanessa gives a fuller answer when the user
    # asks for detail and a one-liner when brevity is requested.
    detail: str = "normal"

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
            "web_search": self.web_search,
            "web_query": self.web_query,
            "needs_clarification": self.needs_clarification,
            "clarification_hint": self.clarification_hint,
            "uses_pro_model": self.uses_pro_model,
            "repeated_topic": self.repeated_topic,
            "loop_level": self.loop_level,
            "detail": self.detail,
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
            result = self._apply_detail(self._fallback(message), message)
            logger.info(
                "turn_plan source=fallback search=%r skip=%s should_reply=%s "
                "tone=%s humor_ok=%s humor_query=%r knowledge=%s knowledge_query=%r "
                "knowledge_detail=%s needs_clarification=%s detail=%s reason=%r",
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
                result.detail,
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
                "web_search=%s web_query=%r needs_clarification=%s "
                "uses_pro_model=%s detail=%s reason=%r",
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
                result.web_search,
                result.web_query,
                result.needs_clarification,
                result.uses_pro_model,
                result.detail,
                result.reason,
            )
        return self._apply_detail(result, message)

    @staticmethod
    def _apply_detail(plan: TurnPlan, message: str) -> TurnPlan:
        """Overlay the deterministic detail heuristic on the planner's verdict.

        Explicit "give me more / keep it short" phrasing in the raw message wins
        over the planner's judgment (the user said what they want); otherwise
        the planner's ``detail`` (default "normal") stands. A clarification turn
        is the exception: it replies with one short question, so no detail
        directive is applied even if the message contains «подробнее».
        """
        heuristic = detect_detail_level(message)
        if plan.needs_clarification:
            detail = "normal"
        elif heuristic in ("brief", "detailed"):
            detail = heuristic
        else:
            detail = plan.detail
        if detail == plan.detail:
            return plan
        return replace(plan, detail=detail)

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
        repeated_topic = payload.get("repeated_topic") is True
        loop_level = _parse_loop_level(payload.get("loop_level"))

        if payload.get("skip") is True:
            return TurnPlan(
                original=original,
                text="",
                skip_search=True,
                should_reply=False,
                repeated_topic=repeated_topic,
                loop_level=loop_level,
                detail=_parse_detail(payload.get("detail")),
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
                detail=_parse_detail(payload.get("detail")),
                repeated_topic=repeated_topic,
                loop_level=loop_level,
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
        # Live web search: the planner flags it when the question needs fresh /
        # external data. ``web_query`` is the search query; when the planner
        # forgot it, fall back to the composed search_query so the search never
        # runs on an empty string.
        web_search = payload.get("web_search") is True
        web_query = str(payload.get("web_query", "")).strip()
        if web_search and not web_query:
            web_query = text
        web_search = web_search and bool(web_query)
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
            web_search=web_search,
            web_query=web_query,
            uses_pro_model=uses_pro_model,
            repeated_topic=repeated_topic,
            loop_level=loop_level,
            detail=_parse_detail(payload.get("detail")),
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


def _parse_loop_level(value: object) -> int:
    """Clamp the planner's loop_level to 0..3 (a bare ``true`` counts as 1)."""
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(3, level))
