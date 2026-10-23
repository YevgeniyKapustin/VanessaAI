"""Turn a Hermes outcome into one follow-up text in Vanessa's persona."""

from __future__ import annotations

import logging
from typing import Any

from services.worker.hermes.payload import HermesAsk
from services.worker.hermes.prompt import build_followup_user_prompt
from vanessa.config.content_hermes import HermesContent
from vanessa.core.protocols import LLMChatCompleter
from vanessa.llm.generation import LLMGenerationParams
from vanessa.pipeline.llm.format.answer_tag import extract_answer, has_ignore_marker
from vanessa.pipeline.llm.format.block_markers import strip_block_markers
from vanessa.pipeline.llm.format.stray_tags import strip_stray_tags

logger = logging.getLogger(__name__)

# ``OutboundMessage.text`` max_length (one Telegram message).
OUTBOUND_MAX_CHARS = 4096
_ELLIPSIS = "…"
LLM_KIND = "hermes_followup"


def truncate_message(text: str, limit: int = OUTBOUND_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


def fallback_text(answer: str | None, prompts: HermesContent) -> str:
    """No LLM text: Hermes' answer as is, or the fixed "did not deliver" line."""
    return truncate_message(answer or prompts.undelivered_fallback)


def final_text(raw: str) -> str:
    """Final message after ``[answer]``; empty for no text or ``[ignore]``."""
    reply, _reasoning = extract_answer(raw)
    reply = strip_block_markers(reply)
    if has_ignore_marker(reply):
        return ""
    return strip_stray_tags(reply).strip()


def chat_request(
    completer: LLMChatCompleter, system: str, user: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Messages + extra kwargs: Anthropic takes ``system`` as a kwarg."""
    if getattr(completer, "provider", "") == "claude":
        return [{"role": "user", "content": user}], {"system": system}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return messages, {}


class FollowupComposer:
    """LLM boundary for the late follow-up (completer + persona prompt)."""

    def __init__(
        self,
        completer: LLMChatCompleter,
        *,
        model: str,
        system_prompt: str,
        prompts: HermesContent,
        generation: LLMGenerationParams,
    ) -> None:
        self._completer = completer
        self._model = model
        self._system = system_prompt
        self._prompts = prompts
        self._generation = generation

    async def compose(self, ask: HermesAsk, answer: str | None) -> str:
        """Always return a non-empty text of at most 4096 characters."""
        try:
            raw = await self._complete(ask, answer)
        except Exception as exc:  # noqa: BLE001 - any LLM failure → plain fallback
            # The type only: provider errors may echo the prompt.
            logger.warning(
                "hermes_followup_llm_failed chat_id=%s error=%s",
                ask.telegram_chat_id,
                type(exc).__name__,
            )
            raw = ""
        text = final_text(raw)
        if not text:
            return fallback_text(answer, self._prompts)
        return truncate_message(text)

    async def _complete(self, ask: HermesAsk, answer: str | None) -> str:
        user = build_followup_user_prompt(ask, answer, self._prompts)
        messages, extra = chat_request(self._completer, self._system, user)
        return await self._completer.complete(
            self._model,
            messages,
            kind=LLM_KIND,
            **self._generation.to_llm_kwargs(),
            **extra,
        )
