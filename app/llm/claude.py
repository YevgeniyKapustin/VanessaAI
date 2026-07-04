import asyncio
import logging

from anthropic import APIStatusError, AsyncAnthropic

from app.config.content import AppContent, get_content
from app.config.settings import settings
from app.core.messages import ContextBlock, ContextMessage
from app.llm.generation_config import LLMGenerationParams
from app.llm.profanity_substitution import ProfanitySubstitutor
from app.llm.prompt_builder import PromptBuilder
from app.llm.reply_format import capitalize_sentences

logger = logging.getLogger(__name__)


class ClaudeLLMProvider:
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

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, APIStatusError):
            return exc.status_code in {429, 500, 502, 503, 529}
        return False

    def _substitute_profanity(self, text: str) -> str:
        substitutor = self._profanity
        if substitutor is None:
            from app.config.content import get_content

            substitutor = ProfanitySubstitutor.from_content(get_content())
        return substitutor.apply(text)

    async def generate(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        system = system_prompt or self._prompts.system_prompt
        user_prompt = self._prompts.build_user_prompt(
            user_message,
            context_blocks,
            session_messages=session_messages,
            humor_quotes=humor_quotes,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
        )
        message_count = sum(len(block.messages) for block in context_blocks)
        logger.info(
            "llm_prompt_prepared model=%s context_blocks=%s context_messages=%s "
            "humor_quotes=%s system_chars=%s user_chars=%s temperature=%s "
            "top_p=%s max_tokens=%s",
            self._model,
            len(context_blocks),
            message_count,
            len(humor_quotes or []),
            len(system),
            len(user_prompt),
            self._generation.temperature,
            self._generation.top_p,
            self._generation.max_tokens,
        )
        logger.info("llm_system_prompt:\n%s", system)
        logger.info("llm_user_prompt:\n%s", user_prompt)

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    system=system,
                    messages=[
                        {
                            "role": "user",
                            "content": user_prompt,
                        }
                    ],
                    **self._generation.to_anthropic_kwargs(),
                )
                return capitalize_sentences(
                    self._substitute_profanity(response.content[0].text)
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self._max_retries or not self._should_retry(exc):
                    raise
                delay = 1.0 * (attempt + 1)
                logger.warning(
                    "LLM request failed (attempt %s/%s), retry in %.1fs: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
        assert last_error is not None
        raise last_error
