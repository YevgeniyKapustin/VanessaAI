from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.core.protocols import LLMChatCompleter
from vanessa.pipeline.decision.turn_plan import TurnPlan
from vanessa.pipeline.llm.planner.detail_detector import detect_detail_level
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.planner.turn_plan_llm import _TurnPlanLlmMixin
from vanessa.pipeline.llm.planner.turn_plan_parse import parse_llm_response

logger = logging.getLogger(__name__)


def apply_detail(plan: TurnPlan, message: str) -> TurnPlan:
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


def fallback_plan(message: str) -> TurnPlan:
    text = message.strip()
    return TurnPlan(
        original=message,
        text=text,
        skip_search=not text,
        should_reply=None,
    )


class TurnPlanner(_TurnPlanLlmMixin):
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
        sender_name: str = "",
        sender_is_owner: bool = False,
    ) -> TurnPlan:
        if not self._use_llm:
            result = apply_detail(fallback_plan(message), message)
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
                sender_name=sender_name,
                sender_is_owner=sender_is_owner,
            )
        except Exception:
            logger.exception(
                "turn_plan failed original=%r, using fallback",
                message,
            )
            result = fallback_plan(message)
        else:
            logger.info(
                "turn_plan source=llm search=%r skip=%s should_reply=%s "
                "tone=%s humor_ok=%s humor_query=%r deep_search=%s "
                "knowledge=%s knowledge_query=%r knowledge_detail=%s "
                "web_search=%s web_query=%r needs_clarification=%s "
                "detail=%s ask_hermes=%s hermes_query=%r "
                "reason=%r",
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
                result.detail,
                result.ask_hermes,
                result.hermes_query,
                result.reason,
            )
        return apply_detail(result, message)

    _apply_detail = staticmethod(apply_detail)
    _fallback = staticmethod(fallback_plan)
    _parse_llm_response = staticmethod(parse_llm_response)
