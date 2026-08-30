from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Pattern

from vanessa.config.content import AppContent, get_content, get_continuation_phrases
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage
from vanessa.decision.detectors.noise import NoiseFilter
from vanessa.decision.gate.continuation import is_sender_continuation_demand
from vanessa.llm.providers.protocols import LLMChatCompleter, create_chat_completer

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_REACTION_GATE_PROMPT",
    "ReactionGate",
    "ReactionGateResult",
]

# Built-in fallback prompt (used only when config/content/decision.yaml does not
# provide ``reaction_gate_prompt``). Kept deliberately tiny: the whole point is a
# single fast, cheap YES/NO call, not a mini-planner.
DEFAULT_REACTION_GATE_PROMPT = (
    "You are a lightweight decision gate for a chat bot \"Ванесса\" in a group "
    "chat. Decide ONLY whether the bot should react to the CURRENT message.\n"
    "Answer with exactly one word: YES or NO. Nothing else.\n"
    "YES — the message is addressed to the bot, asks a question, requests help, "
    "clearly expects the bot's reaction, or is a short follow-up right after "
    "the bot's own reply demanding more (e.g. \"а ещё\"). "
    "Any imperative addressed to the bot by name or \"ты\" "
    "(\"ванесса, не тормози, я написал\", \"ванесса, отвечай\") is an address "
    "to her → YES, even without a question mark. \"Общение между собой\" means "
    "people talking to each other WITHOUT addressing the bot — naming the bot "
    "is not that.\n"
    "NO — people are simply chatting among themselves; the bot's name was "
    "mentioned in passing but no answer is required; a status remark, a "
    "statement, a rhetorical remark, or small talk that does not call for a "
    "reaction.\n\n"
    "Current message:\n{message}\n\n"
    "Recent messages (before the current one):\n{recent}\n\n"
    "Flags:\n"
    "- the message mentions the bot's name: {mentions_bot}\n"
    "- the message is a reply to the bot's message: {reply_to_bot}\n"
    "- the message is a reply to another user: {reply_to_other_user}\n"
    "- the bot is inside a post-reply window: {listen_window}\n\n"
    "Reply with a single word: YES or NO."
)

# Small built-in imperative request verbs, merged with the configured trigger
# keywords. Used by the zero-cost Tier-1 short-circuit so clear requests
# ("скажи", "напиши", "сделай", ...) never pay an LLM call in the gate.
_IMPERATIVE_REQUESTS = frozenset(
    {
        "скажи",
        "напиши",
        "сделай",
        "дай",
        "покажи",
        "кинь",
        "переведи",
        "объясни",
        "помоги",
        "найди",
        "расскажи",
    }
)


@dataclass(frozen=True, slots=True)
class ReactionGateResult:
    """Verdict of the lightweight pre-planner classifier.

    ``respond=True`` means the turn proceeds to the heavy LLM planner;
    ``respond=False`` means the pipeline finalizes immediately (the bot stays
    silent) without spending planner/RAG/compose tokens.
    """

    respond: bool
    reason: str = ""


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
        self._client = llm_client or create_chat_completer()
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

        decision = self._content.decision
        self._question_patterns = tuple(
            _word_boundary_pattern(word)
            for word in (question_words if question_words is not None else decision.question_words)
        )
        self._trigger_keywords = tuple(
            _lower_strip(word)
            for word in (
                trigger_keywords
                if trigger_keywords is not None
                else decision.trigger_keywords
            )
            if _lower_strip(word)
        )
        self._modal_verbs = tuple(
            _lower_strip(word)
            for word in (modal_verbs if modal_verbs is not None else decision.modal_verbs)
            if _lower_strip(word)
        )
        if bot_names is not None:
            names = bot_names
        else:
            names = (*decision.default_bot_names, *settings.bot_name_aliases)
        self._bot_names = frozenset(
            name.lower().strip() for name in names if name and name.strip()
        )
        # Imperative request verbs = built-in set ∪ configured trigger keywords.
        self._imperative_requests = tuple(
            sorted(set(_IMPERATIVE_REQUESTS) | set(self._trigger_keywords))
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
        if not self._enabled:
            return ReactionGateResult(respond=True, reason="disabled")

        # High-confidence bypasses: never risk dropping a direct interaction.
        if self._bypass_reply_to_bot and reply_to_bot:
            return ReactionGateResult(respond=True, reason="reply_to_bot")
        if self._bypass_listen_window and in_listen_window:
            return ReactionGateResult(respond=True, reason="listen_window")

        # Tier 1 — deterministic fast path (microseconds, NO LLM call). Resolves
        # clear requests instantly so the gate adds zero latency on legit turns.
        fast = self._fast_verdict(text, recent_messages, sender_telegram_id)
        if fast is not None:
            return fast

        # Tier 2 — ambiguous tail only: one tiny YES/NO call, fail-open.
        return await self._classify_with_llm(
            text,
            recent_messages,
            mentions_bot=mentions_bot,
            reply_to_bot=reply_to_bot,
            reply_to_other_user=reply_to_other_user,
            in_listen_window=in_listen_window,
        )

    def _fast_verdict(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        sender_telegram_id: int | None = None,
    ) -> ReactionGateResult | None:
        """Tier-1 zero-cost classification. ``None`` = ambiguous → go to LLM."""
        if not self._heuristics_enabled:
            return None
        lowered = text.strip().lower()
        if not lowered:
            # Empty body — let the planner decide (fail open, no cost).
            return ReactionGateResult(respond=True, reason="empty")

        # Direct address at the very start ("ванесса, ...") — clear YES.
        first = lowered.split()[0].rstrip(",:!?") if lowered.split() else ""
        if first in self._bot_names:
            return ReactionGateResult(respond=True, reason="heuristic_address")

        # Clear request signals — clear YES.
        if text.rstrip().endswith("?"):
            return ReactionGateResult(respond=True, reason="heuristic_question")
        if any(pattern.search(lowered) for pattern in self._question_patterns):
            return ReactionGateResult(respond=True, reason="heuristic_question")
        if any(word in lowered for word in self._imperative_requests):
            return ReactionGateResult(respond=True, reason="heuristic_request")
        if any(word in lowered for word in self._modal_verbs):
            return ReactionGateResult(respond=True, reason="heuristic_request")

        # Sender-aware continuation follow-up right after the bot's own reply
        # ("а ещё" = "tell me another one"). Checked before the noise
        # short-circuit so one-word phrases like "давай" still pass as requests.
        if (
            self._continuation_enabled
            and sender_telegram_id
            and is_sender_continuation_demand(
                text,
                recent_messages,
                sender_telegram_id,
                phrases=self._continuation_phrases,
            )
        ):
            return ReactionGateResult(respond=True, reason="heuristic_continuation")

        # Unambiguous filler/acknowledgment ("ок", "ага", "👍") — clear NO
        # (instant short-circuit, no LLM). Short-but-possibly-meaningful
        # messages ("го", "хз", "погнали") are NOT dropped here: they fall
        # through to the Tier-2 LLM so the neural network decides when there
        # is doubt.
        if self._noise_filter.is_definite_noise(text):
            return ReactionGateResult(respond=False, reason="heuristic_noise")

        return None

    async def _classify_with_llm(
        self,
        text: str,
        recent_messages: list[ContextMessage],
        *,
        mentions_bot: bool,
        reply_to_bot: bool,
        reply_to_other_user: bool,
        in_listen_window: bool,
    ) -> ReactionGateResult:
        prompt = self._prompt.format(
            message=text,
            recent=self._format_recent(recent_messages, self._recent_window),
            mentions_bot="yes" if mentions_bot else "no",
            reply_to_bot="yes" if reply_to_bot else "no",
            reply_to_other_user="yes" if reply_to_other_user else "no",
            listen_window="yes" if in_listen_window else "no",
        )
        logger.info(
            "reaction_gate_request model=%s max_tokens=%s recent=%s "
            "mentions_bot=%s reply_to_bot=%s reply_to_other_user=%s listen_window=%s",
            self._model,
            self._max_tokens,
            len(recent_messages),
            mentions_bot,
            reply_to_bot,
            reply_to_other_user,
            in_listen_window,
        )
        try:
            raw = (
                await self._client.complete(
                    self._model,
                    [{"role": "user", "content": prompt}],
                    kind="reaction_gate",
                    max_tokens=self._max_tokens,
                    temperature=0.0,
                )
            ).strip()
        except Exception:
            # Fail-open: a broken classifier must never drop a legitimate turn.
            logger.exception(
                "reaction_gate_failed message=%r, failing open to respond",
                text,
            )
            return ReactionGateResult(respond=True, reason="error")

        head = raw.strip().upper()
        if head.startswith("NO"):
            logger.info(
                "reaction_gate_verdict=no message=%r, finalizing without reply",
                text,
            )
            return ReactionGateResult(respond=False, reason="no")
        if head.startswith("YES"):
            return ReactionGateResult(respond=True, reason="yes")
        # Ambiguous (model did not return a clean YES/NO): fail open.
        logger.warning(
            "reaction_gate_ambiguous raw=%r message=%r, failing open to respond",
            raw,
            text,
        )
        return ReactionGateResult(respond=True, reason="ambiguous")

    @staticmethod
    def _format_recent(
        recent_messages: list[ContextMessage],
        limit: int,
    ) -> str:
        """Compact, bounded rendering of the recent window for the classifier.

        Only the tail of the window is used and every line is truncated, so the
        gate call stays tiny and cheap regardless of conversation length.
        """
        recent = recent_messages[-limit:] if limit > 0 else recent_messages
        if not recent:
            return "(нет)"
        lines: list[str] = []
        for message in recent:
            text = (message.content or "").replace("\n", " ").strip()
            if not text:
                continue
            if len(text) > 200:
                text = text[:200] + "…"
            if message.role == "assistant":
                lines.append(f"[assistant] {text}")
            else:
                sender = (
                    message.sender_name
                    or (
                        f"user{message.sender_telegram_id}"
                        if message.sender_telegram_id
                        else "user"
                    )
                )
                lines.append(f"[{sender}] {text}")
        return "\n".join(lines) or "(нет)"


def _word_boundary_pattern(word: str) -> Pattern[str]:
    return re.compile(rf"\b{re.escape(word.strip().lower())}\b", re.IGNORECASE)


def _lower_strip(word: str) -> str:
    return word.strip().lower()
