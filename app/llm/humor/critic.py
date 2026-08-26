from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.config.content import AppContent, get_content
from app.config.settings import settings
from app.llm.format.llm_json import normalize_llm_json
from app.llm.planner.generation_config import LLMGenerationParams
from app.llm.providers.protocols import LLMChatCompleter, create_chat_completer

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = """\
You are a humor editor (the Critic). You review a draft reply of the chat bot for
safety, quality and appropriateness of humor.

Review criteria:
1. Pattern hit: the reply contains the claimed humor (incongruity,
   hyperbole, irony, a reference to a recognizable chat meme), not a boring
   brush-off or a flat cliché.
2. Safety: no direct insults, threats or harmful content.
3. Appropriateness: the humor matches the tone of the chat and doesn't hurt the bot's owner.
4. Coherence: the reply answers the user's message.

Response format — strictly JSON without markdown:
{
  "status": "APPROVED" or "REJECTED",
  "score": a number from 1 to 5,
  "reason": "why this verdict was made",
  "fix_instruction": "instruction to the generator on how to improve (empty string if APPROVED)"
}
"""


class CriticStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class CriticVerdict:
    status: CriticStatus
    score: int
    reason: str = ""
    fix_instruction: str = ""

    @property
    def approved(self) -> bool:
        return self.status is CriticStatus.APPROVED


def _fallback_user_prompt(
    user_message: str,
    draft: str,
    humor_quotes: str,
) -> str:
    return (
        f"User's message:\n{user_message}\n\n"
        f"Recognizable chat memes:\n{humor_quotes}\n\n"
        f"Draft of the bot's reply:\n{draft}"
    )


def parse_critic_verdict(raw: str) -> CriticVerdict:
    """Parse the critic's JSON reply into a verdict.

    Fail-open: any parse/validation problem degrades to APPROVED so the
    pipeline never blocks a reply because of a malformed critic response.
    """
    normalized = normalize_llm_json(raw)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        logger.warning(
            "humor_critic unparseable json, fallback APPROVED: %r",
            raw[:200],
        )
        return CriticVerdict(status=CriticStatus.APPROVED, score=3, reason="unparseable response")

    if not isinstance(payload, dict):
        logger.warning("humor_critic non-object payload, fallback APPROVED: %r", payload)
        return CriticVerdict(status=CriticStatus.APPROVED, score=3, reason="non-object response")

    status = _parse_status(payload.get("status"))
    if status is None:
        logger.warning(
            "humor_critic invalid status %r, fallback APPROVED",
            payload.get("status"),
        )
        status = CriticStatus.APPROVED

    return CriticVerdict(
        status=status,
        score=_clamp_score(payload.get("score")),
        reason=_clean_text(payload.get("reason")),
        fix_instruction=_clean_text(payload.get("fix_instruction")),
    )


def _parse_status(value: object) -> CriticStatus | None:
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized == "APPROVED":
            return CriticStatus.APPROVED
        if normalized == "REJECTED":
            return CriticStatus.REJECTED
    return None


def _clamp_score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, score))


def _clean_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


class HumorCritic:
    """Agent that reviews a generated draft and returns a structured verdict."""

    def __init__(
        self,
        content: AppContent | None = None,
        *,
        llm_client: LLMChatCompleter | None = None,
        model: str | None = None,
        generation: LLMGenerationParams | None = None,
    ) -> None:
        self._content = content or get_content()
        self._client = llm_client
        self._model = model or settings.resolved_critic_model
        self._generation = (
            generation or self._content.llm.generation.critic.to_params()
        )

    @property
    def _completer(self) -> LLMChatCompleter:
        if self._client is None:
            self._client = create_chat_completer()
        return self._client

    async def review(
        self,
        draft: str,
        *,
        user_message: str,
        humor_quotes: list[str],
    ) -> CriticVerdict:
        critic = self._content.llm.critic
        system = critic.system_prompt.strip() or _DEFAULT_SYSTEM_PROMPT
        quotes_text = "\n".join(f"- {quote}" for quote in humor_quotes) or "(none)"
        template = critic.user_prompt.strip()
        if template:
            user_prompt = template.format(
                user_message=user_message,
                draft=draft,
                humor_quotes=quotes_text,
            )
        else:
            user_prompt = _fallback_user_prompt(user_message, draft, quotes_text)

        try:
            raw = (
                await self._completer.complete(
                    self._model,
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    **self._generation.to_llm_kwargs(),
                )
            ).strip()
        except Exception:
            logger.exception(
                "humor_critic request failed, fallback APPROVED "
                "(model=%s, draft_len=%s)",
                self._model,
                len(draft),
            )
            return CriticVerdict(
                status=CriticStatus.APPROVED,
                score=3,
                reason="critic unavailable",
            )
        return parse_critic_verdict(raw)


__all__ = [
    "CriticStatus",
    "CriticVerdict",
    "HumorCritic",
    "parse_critic_verdict",
]
