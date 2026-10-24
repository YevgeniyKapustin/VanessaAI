import asyncio
from typing import Any

from openai import AsyncOpenAI

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.generate_request import GenerateRequest, as_generate_request
from vanessa.core.messages import ContextBlock, ImageAttachment
from vanessa.pipeline.llm.format.profanity_substitution import ProfanitySubstitutor
from vanessa.pipeline.llm.planner.generation_config import LLMGenerationParams
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.llm.providers.deepseek_completion import (
    _DeepSeekCompletionMixin,
)
from vanessa.pipeline.llm.providers.deepseek_usage import (
    _usage_from_openai,
    log_deepseek_prompt,
)


class DeepSeekLLMProvider(_DeepSeekCompletionMixin):
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        prompt_builder: PromptBuilder | None = None,
        profanity_substitutor: ProfanitySubstitutor | None = None,
        max_retries: int | None = None,
        generation: LLMGenerationParams | None = None,
        content: AppContent | None = None,
        vision_model: str | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = client
        self._model = model or settings.deepseek_model
        # Multimodal model for turns that carry images (vision). Selected
        # per-call when generate(images=[...]) is non-empty.
        self._vision_model = vision_model or settings.deepseek_vision_model
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

    @property
    def _openai_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client

    def _resolve_model(self, *, uses_vision: bool) -> str:
        if uses_vision:
            return self._vision_model
        return self._model

    def _user_message_content(
        self,
        user_prompt: str,
        images: list[ImageAttachment] | None,
    ) -> str | list[dict[str, Any]]:
        if not images:
            return user_prompt
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image.data_url}}
            for image in images
        )
        return content

    async def _retry_sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)

    async def generate(
        self,
        user_message: str | GenerateRequest,
        context_blocks: list[ContextBlock] | None = None,
        **kwargs: Any,
    ) -> str:
        request = as_generate_request(user_message, context_blocks, **kwargs)
        uses_vision = bool(request.images)
        model = self._resolve_model(uses_vision=uses_vision)
        system = request.system_prompt or self._prompts.system_prompt
        user_prompt = self._prompts.build_user_prompt(request)
        generation_kwargs = self._generation.to_llm_kwargs()
        if (
            request.detail == "detailed"
            and self._content.llm.detailed_max_tokens > 0
        ):
            generation_kwargs["max_tokens"] = self._content.llm.detailed_max_tokens
        log_deepseek_prompt(
            request,
            model=model,
            system=system,
            user_prompt=user_prompt,
            temperature=self._generation.temperature,
            top_p=self._generation.top_p,
            max_tokens=generation_kwargs.get("max_tokens"),
        )
        return await self._run_completion(
            model=model,
            system=system,
            user_prompt=user_prompt,
            user_content=self._user_message_content(
                user_prompt, request.images if uses_vision else None
            ),
            sender_name=request.sender_name,
            uses_vision=uses_vision,
            image_count=len(request.images or []),
            generation_kwargs=generation_kwargs,
        )


__all__ = ["DeepSeekLLMProvider", "_usage_from_openai"]
