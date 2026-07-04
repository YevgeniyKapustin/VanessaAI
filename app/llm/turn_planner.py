from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from app.config.content import AppContent, get_content
from app.config.settings import settings
from app.core.messages import ContextMessage
from app.core.nicknames import format_nicknames_for_planner
from app.llm.session_format import format_session_messages, session_context_messages

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TurnPlan:
    original: str
    text: str
    skip_search: bool
    humor_ok: bool = False
    humor_query: str = ""
    should_reply: bool | None = None


class TurnPlanner:
    def __init__(
        self,
        content: AppContent | None = None,
        *,
        use_llm: bool | None = None,
        llm_client: AsyncAnthropic | None = None,
        llm_model: str | None = None,
    ) -> None:
        self._content = content or get_content()
        self._use_llm = (
            use_llm
            if use_llm is not None
            else settings.rag_query_rewrite_use_llm
        )
        self._client = llm_client
        self._model = llm_model or settings.anthropic_model

    async def prepare(
        self,
        message: str,
        recent_messages: list[ContextMessage] | None = None,
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
    ) -> TurnPlan:
        if not self._use_llm:
            result = self._fallback(message)
            logger.info(
                "turn_plan source=fallback search=%r skip=%s should_reply=%s "
                "humor_ok=%s humor_query=%r",
                result.text,
                result.skip_search,
                result.should_reply,
                result.humor_ok,
                result.humor_query,
            )
            return result

        try:
            result = await self._plan_with_llm(
                message,
                recent_messages or [],
                mentions_bot=mentions_bot,
                reply_to_bot=reply_to_bot,
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
                "humor_ok=%s humor_query=%r",
                result.text,
                result.skip_search,
                result.should_reply,
                result.humor_ok,
                result.humor_query,
            )
        return result

    async def _plan_with_llm(
        self,
        message: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
    ) -> TurnPlan:
        client = self._client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        prompt = self._content.rag.planner_prompt.format(
            message=message,
            recent_messages=self._format_recent(recent_messages) or "(нет)",
            nicknames=format_nicknames_for_planner(),
            mentions_bot="да" if mentions_bot else "нет",
            reply_to_bot="да" if reply_to_bot else "нет",
        )
        response = await client.messages.create(
            model=self._model,
            max_tokens=settings.rag_query_rewrite_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        return self._parse_llm_response(message, raw)

    @staticmethod
    def _normalize_llm_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text

    def _parse_llm_response(self, original: str, raw: str) -> TurnPlan:
        normalized = self._normalize_llm_json(raw)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            payload = {"search_query": normalized, "skip": False}

        if payload.get("skip") is True:
            return TurnPlan(
                original=original,
                text="",
                skip_search=True,
                should_reply=False,
            )

        text = str(payload.get("search_query", "")).strip()
        humor_ok = payload.get("humor_ok") is True
        humor_query = str(payload.get("humor_query", "")).strip()
        if humor_ok and not humor_query:
            humor_ok = False
        should_reply = _parse_should_reply(payload.get("should_reply"))
        return TurnPlan(
            original=original,
            text=text,
            skip_search=not text,
            humor_ok=humor_ok,
            humor_query=humor_query if humor_ok else "",
            should_reply=should_reply,
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
        limit = settings.decision_session_window_size
        return format_session_messages(prior[-limit:], self._content)


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
