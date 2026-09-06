import asyncio
import logging
from dataclasses import replace
from typing import Any

from anthropic import AsyncAnthropic

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.generate_request import (
    GenerateRequest,
    as_generate_request,
    prompt_log_counts,
)
from vanessa.core.messages import ContextBlock
from vanessa.pipeline.llm.format.profanity_substitution import ProfanitySubstitutor
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.llm.providers.claude_completion import _ClaudeCompletionMixin

logger = logging.getLogger(__name__)


def log_claude_prompt(
    request: GenerateRequest,
    *,
    model: str,
    system: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: object,
) -> None:
    message_count, knowledge_chars, session_chars = prompt_log_counts(request)
    logger.info(
        "llm_prompt_prepared model=%s detail=%s context_blocks=%s "
        "context_messages=%s humor_quotes=%s meme_blocks=%s meme_menu=%s "
        "system_chars=%s user_chars=%s knowledge_blocks=%s web_blocks=%s "
        "knowledge_chars=%s session_chars=%s temperature=%s top_p=%s "
        "max_tokens=%s",
        model,
        request.detail,
        len(request.context_blocks),
        message_count,
        len(request.humor_quotes or []),
        len(request.meme_blocks or []),
        len(request.meme_menu or []),
        len(system),
        len(user_prompt),
        len(request.knowledge_blocks or []),
        len(request.web_blocks or []),
        knowledge_chars,
        session_chars,
        temperature,
        top_p,
        max_tokens,
    )
    logger.info("llm_system_prompt:\n%s", system)
    logger.info("llm_user_prompt:\n%s", user_prompt)


class ClaudeLLMProvider(_ClaudeCompletionMixin):
    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        model: str | None = None,
        prompt_builder: PromptBuilder | None = None,
        profanity_substitutor: ProfanitySubstitutor | None = None,
        max_retries: int | None = None,
        generation: LLMGenerationParams | None = None,
        content: AppContent | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.anthropic_model
        self._prompts = prompt_builder or PromptBuilder(self._content)
        self._profanity = profanity_substitutor
        self._max_retries = (
            max_retries
            if max_retries is not None
            else settings.llm_max_retries
        )
        self._generation = (
            generation
            or self._content.llm.generation.composer.to_params()
        )

    async def _retry_sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)

    async def generate(
        self,
        user_message: str | GenerateRequest,
        context_blocks: list[ContextBlock] | None = None,
        **kwargs: Any,
    ) -> str:
        request = as_generate_request(user_message, context_blocks, **kwargs)
        # Vision fields are DeepSeek routing signals; Claude accepts them for
        # protocol compatibility but must not inject them into the prompt.
        prompt_request = replace(
            request,
            images=None,
            photo_candidates=None,
            current_images=None,
        )
        system = request.system_prompt or self._prompts.system_prompt
        user_prompt = self._prompts.build_user_prompt(prompt_request)
        generation_kwargs = self._generation.to_llm_kwargs()
        # ``reasoning_effort`` is DeepSeek-only (V4 thinking models). Claude has
        # its own extended-thinking API and would 400 on an unknown param, so
        # strip it here; the in-prompt chain-of-thought still applies on Claude.
        generation_kwargs.pop("reasoning_effort", None)
        if (
            request.detail == "detailed"
            and self._content.llm.detailed_max_tokens > 0
        ):
            generation_kwargs["max_tokens"] = self._content.llm.detailed_max_tokens
        log_claude_prompt(
            request,
            model=self._model,
            system=system,
            user_prompt=user_prompt,
            temperature=self._generation.temperature,
            top_p=self._generation.top_p,
            max_tokens=generation_kwargs.get("max_tokens"),
        )
        return await self._run_completion(
            system=system,
            user_prompt=user_prompt,
            sender_name=request.sender_name,
            generation_kwargs=generation_kwargs,
        )
