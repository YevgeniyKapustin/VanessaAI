"""MemoryPlanner: LLM decision over a recent-message transcript -> MemoryPlan."""

from __future__ import annotations

import json
import logging

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.knowledge.schema import MemoryPlan
from vanessa.knowledge.users.nicknames import format_nicknames_for_planner
from vanessa.pipeline.llm.format.llm_json import normalize_llm_json
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.providers.protocols import LLMChatCompleter, create_chat_completer

logger = logging.getLogger(__name__)


class MemoryPlanner:
    def __init__(
        self,
        content: AppContent | None = None,
        *,
        llm_client: LLMChatCompleter | None = None,
        llm_model: str | None = None,
        generation: LLMGenerationParams | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = llm_client
        self._model = llm_model or settings.knowledge_model or settings.planner_model
        self._generation = generation or LLMGenerationParams(
            temperature=0.1,
            top_p=0.85,
            max_tokens=settings.knowledge_memory_max_tokens,
        )

    async def decide(self, transcript: str) -> MemoryPlan:
        prompt = self._content.memory.extraction_prompt.format(
            transcript=transcript,
            nicknames=format_nicknames_for_planner(),
        )
        client = self._client or create_chat_completer()
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="memory",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        return self._parse(raw)

    def _parse(self, raw: str) -> MemoryPlan:
        normalized = normalize_llm_json(raw)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return MemoryPlan()
        if not isinstance(payload, dict):
            return MemoryPlan()
        updates = payload.get("updates")
        if not isinstance(updates, list):
            return MemoryPlan()
        valid = tuple(u for u in updates if isinstance(u, dict))
        weekly_hint = str(payload.get("weekly_hint") or "").strip()
        return MemoryPlan(updates=valid, weekly_hint=weekly_hint)
