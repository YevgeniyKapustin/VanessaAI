"""LLM call that compresses one People dossier into a compact portrait."""

from __future__ import annotations

import re

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.protocols import LLMChatCompleter
from vanessa.llm.completers import create_chat_completer
from vanessa.llm.generation import LLMGenerationParams


def clean_portrait(raw: str) -> str:
    """Trim fences and collapse whitespace/newlines into a short prose block."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    # A portrait is a short prose block: fold newlines into spaces.
    return " ".join(text.split()).strip()


class PortraitPlanner:
    """LLM call that compresses one dossier into a compact portrait."""

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
            or settings.knowledge_portrait_model
            or settings.knowledge_model
            or settings.planner_model
        )
        self._generation = generation or LLMGenerationParams(
            temperature=0.2,
            top_p=0.85,
            max_tokens=settings.knowledge_portrait_max_tokens,
        )

    async def portrait(
        self,
        *,
        nickname: str,
        aliases: list[str],
        mood: str,
        dossier: str,
        previous_portrait: str = "",
    ) -> str:
        alias_text = ", ".join(alias for alias in aliases if alias and alias != nickname)
        prompt = self._content.portrait.portrait_prompt.format(
            nickname=nickname,
            aliases=alias_text or nickname,
            mood=mood or "unknown",
            dossier=dossier,
            previous_portrait=(previous_portrait or "").strip() or "(нет)",
        )
        client = self._client or create_chat_completer()
        raw = (
            await client.complete(
                self._model,
                [{"role": "user", "content": prompt}],
                kind="portrait",
                **self._generation.to_llm_kwargs(),
            )
        ).strip()
        return clean_portrait(raw)
