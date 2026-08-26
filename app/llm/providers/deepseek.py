import asyncio
import logging

from openai import APIStatusError, AsyncOpenAI

from app.config.content import AppContent, MemeDefContent, get_content
from app.config.settings import settings
from app.core.messages import ContextBlock, ContextMessage
from app.knowledge.schema import KnowledgeBlock
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.format.profanity_substitution import ProfanitySubstitutor
from app.llm.prompts.prompt_builder import PromptBuilder
from app.llm.format.reply_format import capitalize_sentences

logger = logging.getLogger(__name__)


class DeepSeekLLMProvider:
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        prompt_builder: PromptBuilder | None = None,
        profanity_substitutor: ProfanitySubstitutor | None = None,
        max_retries: int | None = None,
        generation: LLMGenerationParams | None = None,
        content: AppContent | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = client
        self._model = model or settings.deepseek_model
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
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        meme_blocks: list[MemeDefContent] | None = None,
        meme_menu: list[MemeDefContent] | None = None,
        metrics_block: str | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        system_prompt: str | None = None,
        critic_feedback: str | None = None,
        tone: str | None = None,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
    ) -> str:
        system = system_prompt or self._prompts.system_prompt
        user_prompt = self._prompts.build_user_prompt(
            user_message,
            context_blocks,
            session_messages=session_messages,
            humor_quotes=humor_quotes,
            knowledge_blocks=knowledge_blocks,
            meme_blocks=meme_blocks,
            meme_menu=meme_menu,
            metrics_block=metrics_block,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
            critic_feedback=critic_feedback,
            tone=tone,
            reply_to_text=reply_to_text,
            reply_to_sender_telegram_id=reply_to_sender_telegram_id,
            reply_to_sender_name=reply_to_sender_name,
        )
        message_count = sum(len(block.messages) for block in context_blocks)
        logger.info(
            "llm_prompt_prepared model=%s context_blocks=%s context_messages=%s "
            "humor_quotes=%s meme_blocks=%s meme_menu=%s system_chars=%s "
            "user_chars=%s temperature=%s top_p=%s max_tokens=%s",
            self._model,
            len(context_blocks),
            message_count,
            len(humor_quotes or []),
            len(meme_blocks or []),
            len(meme_menu or []),
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
                response = await self._openai_client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    **self._generation.to_llm_kwargs(),
                )
                text = response.choices[0].message.content or ""
                return capitalize_sentences(
                    self._substitute_profanity(text)
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
