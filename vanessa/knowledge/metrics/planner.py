"""MetricsPlanner: LLM semantic scoring of a transcript -> MetricsSnapshot list."""

from __future__ import annotations

import json
import logging

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.protocols import LLMChatCompleter
from vanessa.knowledge.metrics.schema import MetricsSnapshot, PersonMetrics
from vanessa.knowledge.users.nicknames import format_nicknames_for_planner
from vanessa.llm.completers import create_chat_completer
from vanessa.llm.generation import LLMGenerationParams
from vanessa.llm.json_text import normalize_llm_json

logger = logging.getLogger(__name__)


class MetricsPlanner:
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
        self._model = (
            llm_model
            or settings.knowledge_metrics_model
            or settings.knowledge_model
            or settings.planner_model
        )
        self._generation = generation or LLMGenerationParams(
            temperature=0.1,
            top_p=0.85,
            max_tokens=settings.knowledge_metrics_max_tokens,
        )

    async def decide(self, transcript: str) -> tuple[MetricsSnapshot, ...]:
        prompt = self._content.metrics.extraction_prompt.format(
            transcript=transcript,
            nicknames=format_nicknames_for_planner(),
        )
        client = self._client or create_chat_completer()
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="metrics",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        return self._parse(raw)

    def _parse(self, raw: str) -> tuple[MetricsSnapshot, ...]:
        normalized = normalize_llm_json(raw)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, dict):
            return ()
        snapshots = payload.get("snapshots")
        if not isinstance(snapshots, list):
            snapshots = payload.get("updates")
        if not isinstance(snapshots, list):
            return ()
        result: list[MetricsSnapshot] = []
        for item in snapshots:
            if not isinstance(item, dict):
                continue
            person = str(item.get("person") or "").strip()
            if not person:
                continue
            metrics_data = item.get("metrics")
            if not isinstance(metrics_data, dict):
                continue
            telegram_id = item.get("telegram_id")
            result.append(
                MetricsSnapshot(
                    person=person,
                    metrics=PersonMetrics.from_dict(metrics_data),
                    telegram_id=(
                        int(telegram_id) if telegram_id is not None else None
                    ),
                )
            )
        return tuple(result)
