"""RAG Triad evaluation (context relevance / groundedness / answer relevance).

Deterministic signals (retrieval score histograms, empty-retrieval counter,
context length) are collected continuously by :mod:`app.observability.metrics`.
This module adds the sampled LLM-as-judge evaluation that runs in the
background after a reply and reports scores via ``vanessa_rag_eval_score``.

Off by default (``RAG_EVAL_ENABLED=false``); ``RagTriadEvaluator.should_run``
gates the sampling so enabling the feature never changes reply latency.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any

from app.config.settings import settings
from app.llm.format.llm_json import normalize_llm_json
from app.llm.providers.protocols import LLMChatCompleter, create_chat_completer
from app.observability.metrics import record_rag_eval

logger = logging.getLogger(__name__)

DIMENSIONS = ("context_relevance", "groundedness", "answer_relevance")

_JUDGE_PROMPT = """\
You are an evaluator of a Retrieval-Augmented Generation (RAG) chatbot. Judge a single turn.

Question (user):
{question}

Retrieved context:
{context}

Answer (bot):
{answer}

Score each dimension from 0.0 to 1.0:
- context_relevance: does the retrieved context actually help answer the question? (low = retrieval missed the topic)
- groundedness: is the answer fully supported by the context, without hallucinated facts? (low = unsupported claims)
- answer_relevance: does the answer directly address the user's question? (low = off-topic)

Return ONLY JSON without markdown:
{{"context_relevance": 0.0, "groundedness": 0.0, "answer_relevance": 0.0, "reasons": {{"context_relevance": "...", "groundedness": "...", "answer_relevance": "..."}}}}
"""


def _clamp(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


class RagTriadEvaluator:
    """LLM-as-judge evaluation of the RAG Triad. Fail-open: never raises."""

    def __init__(
        self,
        *,
        completer: LLMChatCompleter | None = None,
        model: str | None = None,
        enabled: bool | None = None,
        sample_rate: float | None = None,
    ) -> None:
        self._completer = completer
        self._model = model or settings.rag_eval_model or settings.planner_model
        self._enabled = settings.rag_eval_enabled if enabled is None else enabled
        self._sample_rate = (
            settings.rag_eval_sample_rate if sample_rate is None else sample_rate
        )

    def should_run(self) -> bool:
        """Whether the current turn should be evaluated (feature + sampling)."""
        if not self._enabled:
            return False
        if self._sample_rate >= 1.0:
            return True
        if self._sample_rate <= 0.0:
            return False
        return random.random() < self._sample_rate

    async def evaluate(
        self,
        *,
        question: str,
        answer: str,
        context: str,
    ) -> dict[str, float]:
        """Run the judge once and record metrics.

        Returns a dict of the three scores (0..1) on success, {} on failure.
        """
        prompt = _JUDGE_PROMPT.format(
            question=question,
            context=context or "(no context)",
            answer=answer,
        )
        completer = self._completer or create_chat_completer()
        try:
            raw = (
                await completer.complete(
                    self._model,
                    [{"role": "user", "content": prompt}],
                    kind="eval",
                    temperature=0.0,
                    max_tokens=512,
                )
            ).strip()
        except Exception:
            logger.exception("rag_eval_judge_failed")
            return {}

        payload = self._parse(raw)
        if not payload:
            return {}

        scores = {dimension: _clamp(payload.get(dimension)) for dimension in DIMENSIONS}
        for dimension, score in scores.items():
            record_rag_eval(dimension, score)
        return scores

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        normalized = normalize_llm_json(raw)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            logger.warning("rag_eval unparseable judge response: %r", raw[:200])
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload
