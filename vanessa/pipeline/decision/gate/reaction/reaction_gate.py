from __future__ import annotations

from vanessa.config.content import AppContent, get_content, get_continuation_phrases
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.core.protocols import LLMChatCompleter
from vanessa.pipeline.decision.detectors.noise import NoiseFilter
from vanessa.pipeline.decision.gate.reaction.reaction_gate_bypass import (
    gate_bypass_result,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate_heuristics import (
    build_reaction_lexicon,
    fast_verdict,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate_llm import (
    classify_with_llm,
)
from vanessa.pipeline.decision.gate.reaction.reaction_gate_prompt import (
    DEFAULT_REACTION_GATE_PROMPT,
    ReactionGateResult,
)

__all__ = [
    "DEFAULT_REACTION_GATE_PROMPT",
    "ReactionGate",
    "ReactionGateResult",
]


class ReactionGate:
    """Two-tier lightweight Decision Gate that runs BEFORE the LLM turn planner.

    Answers one binary question — "does this message actually require a bot
    reaction?" — as cheaply as possible:

    **Tier 1 (zero-cost, no LLM, microseconds)** — deterministic short-circuits
    from cheap string signals resolve the clear cases:
    - clear request (``?``, question word, trigger keyword, modal or imperative
      request verb) or a direct address at the start of the message
      → ``respond=True`` with NO LLM call and NO added latency on legit turns;
    - obvious noise → ``respond=False`` (instant short-circuit, no LLM).

    **Tier 2 (cheap LLM, ambiguous tail only)** — messages Tier 1 cannot
    resolve (a bot name mentioned mid-sentence, a statement that might be side
    talk) get ONE tiny YES/NO call on the fastest non-reasoning model.

    ``NO`` from either tier short-circuits the whole pipeline instantly: the
    bot writes nothing and the planner/RAG/compose chain is never invoked.
    **Fail-open**: any error or ambiguous response defaults to ``respond=True``
    so a broken classifier can never drop a legitimate turn. High-confidence
    bypasses (a direct reply to the bot's message, a post-reply listen window)
    are never classified.
    """

    def __init__(
        self,
        content: AppContent | None = None,
        *,
        llm_client: LLMChatCompleter | None = None,
        model: str | None = None,
        prompt: str | None = None,
        enabled: bool | None = None,
        max_tokens: int | None = None,
        recent_window: int | None = None,
        bypass_reply_to_bot: bool | None = None,
        bypass_listen_window: bool | None = None,
        heuristics_enabled: bool | None = None,
        continuation_enabled: bool | None = None,
        continuation_phrases: tuple[str, ...] | None = None,
        question_words: tuple[str, ...] | None = None,
        trigger_keywords: tuple[str, ...] | None = None,
        modal_verbs: tuple[str, ...] | None = None,
        bot_names: tuple[str, ...] | None = None,
    ) -> None:
        self._content = content or get_content()
        self._noise_filter = NoiseFilter()
        self._client = llm_client
        self._model = (
            model
            or settings.decision_reaction_gate_model
            or settings.planner_model
        )
        self._prompt = (
            prompt
            if prompt is not None
            else (
                self._content.decision.reaction_gate_prompt
                or DEFAULT_REACTION_GATE_PROMPT
            )
        )
        self._enabled = (
            enabled
            if enabled is not None
            else settings.decision_reaction_gate_enabled
        )
        self._max_tokens = (
            max_tokens
            if max_tokens is not None
            else settings.decision_reaction_gate_max_tokens
        )
        self._recent_window = (
            recent_window
            if recent_window is not None
            else settings.decision_reaction_gate_recent_window
        )
        self._bypass_reply_to_bot = (
            bypass_reply_to_bot
            if bypass_reply_to_bot is not None
            else settings.decision_reaction_gate_bypass_reply_to_bot
        )
        self._bypass_listen_window = (
            bypass_listen_window
            if bypass_listen_window is not None
            else settings.decision_reaction_gate_bypass_listen_window
        )
        self._heuristics_enabled = (
            heuristics_enabled
            if heuristics_enabled is not None
            else settings.decision_reaction_gate_heuristics_enabled
        )
        self._continuation_enabled = (
            continuation_enabled
            if continuation_enabled is not None
            else settings.decision_continuation_follow_up_enabled
        )
        self._continuation_phrases = (
            continuation_phrases
            if continuation_phrases is not None
            else get_continuation_phrases()
        )
        (
            self._question_patterns,
            self._trigger_keywords,
            self._modal_verbs,
            self._bot_names,
            self._imperative_requests,
        ) = build_reaction_lexicon(
            self._content.decision,
            question_words=question_words,
            trigger_keywords=trigger_keywords,
            modal_verbs=modal_verbs,
            bot_names=bot_names,
        )

    async def evaluate(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool = False,
        reply_to_bot: bool = False,
        reply_to_other_user: bool = False,
        in_listen_window: bool = False,
        sender_telegram_id: int | None = None,
    ) -> ReactionGateResult:
        bypassed = gate_bypass_result(
            enabled=self._enabled,
            bypass_reply_to_bot=self._bypass_reply_to_bot,
            reply_to_bot=reply_to_bot,
            bypass_listen_window=self._bypass_listen_window,
            in_listen_window=in_listen_window,
        )
        if bypassed is not None:
            return bypassed

        # Tier 1 — deterministic fast path (microseconds, NO LLM call). Resolves
        # clear requests instantly so the gate adds zero latency on legit turns.
        fast = fast_verdict(
            text,
            recent_messages,
            sender_telegram_id,
            heuristics_enabled=self._heuristics_enabled,
            noise_filter=self._noise_filter,
            bot_names=self._bot_names,
            question_patterns=self._question_patterns,
            imperative_requests=self._imperative_requests,
            modal_verbs=self._modal_verbs,
            continuation_enabled=self._continuation_enabled,
            continuation_phrases=self._continuation_phrases,
        )
        if fast is not None:
            return fast

        # Tier 2 — ambiguous tail only: one tiny YES/NO call, fail-open.
        return await classify_with_llm(
            text,
            recent_messages,
            client=self._client,
            model=self._model,
            prompt=self._prompt,
            max_tokens=self._max_tokens,
            recent_window=self._recent_window,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            in_listen_window=in_listen_window,
        )
