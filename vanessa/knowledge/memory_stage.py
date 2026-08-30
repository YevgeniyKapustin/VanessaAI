"""MemoryStage: post-reply extraction of durable knowledge from recent chat.

Runs after the bot has composed and finalized a reply (fail-open: any failure
is swallowed so the visible reply is never affected). Before spending an LLM
call the stage applies three cheap gates, in order:

- per-chat cooldown (the stage is built per request in the DI container, so the
  cooldown and watermark live at class level — otherwise they reset every turn);
- a per-chat watermark so only messages newer than the last processed run are
  ever handed to the planner (no repeated analysis of the same window);
- a deterministic prefilter ("is there anything to remember") that skips the LLM
  when the new transcript is mundane and would only produce an empty result.
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from vanessa.core.messages import ContextMessage
from vanessa.knowledge.memory_planner import MemoryPlanner
from vanessa.knowledge.memory_prefilter import should_extract_memory
from vanessa.knowledge.people import canonical_name_for_telegram_id
from vanessa.knowledge.writer import KnowledgeVaultWriter
from vanessa.pipeline.llm.prompts.context_format import format_message_time

logger = logging.getLogger(__name__)

# Sentinel chat key for callers that cannot provide a real chat id.
_GLOBAL_CHAT_KEY = 0


def format_memory_transcript(messages: list[ContextMessage]) -> str:
    """Render recent messages for the memory planner.

    Senders are labelled with their canonical nickname (from
    ``config/nicknames.yaml``) and their telegram id, so the planner outputs
    stable ``person`` references that the writer resolves to a single card —
    instead of inventing new spellings like «ну я», «капуст», «владимир».
    """
    lines: list[str] = []
    for message in messages:
        text = message.content.replace("\n", " ").strip()
        if not text:
            continue
        time_label = format_message_time(message.created_at)
        if message.role == "assistant":
            lines.append(f"{time_label} [assistant] {text}")
            continue
        sender = (
            canonical_name_for_telegram_id(message.sender_telegram_id)
            or message.sender_name
            or (str(message.sender_telegram_id) if message.sender_telegram_id else "")
            or "user"
        )
        if message.sender_telegram_id is not None:
            lines.append(
                f"{time_label} [user:{sender} (id:{message.sender_telegram_id})] {text}"
            )
        else:
            lines.append(f"{time_label} [user:{sender}] {text}")
    return "\n".join(lines)


class MemoryStage:
    # Shared across instances: the DI container builds a MemoryStage per request,
    # so any per-instance throttling would reset every turn and memory would run
    # after every reply. The cooldown and the "last processed message" watermark
    # therefore live at class level, keyed by chat (the same pattern the metrics
    # pipeline already uses for its cooldown). In-memory state resets on restart;
    # the periodic sweep remains the durable fallback for missed messages.
    _last_run_by_chat: ClassVar[dict[int, float]] = {}
    _last_message_id_by_chat: ClassVar[dict[int, int]] = {}

    def __init__(
        self,
        writer: KnowledgeVaultWriter,
        planner: MemoryPlanner,
        *,
        enabled: bool = True,
        cooldown_seconds: int = 300,
        prefilter_enabled: bool = True,
        prefilter_min_messages: int = 1,
        prefilter_min_content_chars: int = 40,
        prefilter_score_threshold: float = 1.5,
    ) -> None:
        self._writer = writer
        self._planner = planner
        self._enabled = enabled
        self._cooldown = cooldown_seconds
        self._prefilter_enabled = prefilter_enabled
        self._prefilter_min_messages = prefilter_min_messages
        self._prefilter_min_content_chars = prefilter_min_content_chars
        self._prefilter_score_threshold = prefilter_score_threshold

    @classmethod
    def _chat_key(cls, telegram_chat_id: int | None) -> int:
        return telegram_chat_id if telegram_chat_id is not None else _GLOBAL_CHAT_KEY

    async def run(
        self,
        *,
        recent_messages: list[ContextMessage],
        source_message_ids: list[int] | None = None,
        telegram_chat_id: int | None = None,
    ) -> int:
        if not self._enabled or not recent_messages:
            return 0
        chat_key = self._chat_key(telegram_chat_id)

        # Gate 1: per-chat cooldown.
        now = time.monotonic()
        if self._cooldown > 0:
            last_run = type(self)._last_run_by_chat.get(chat_key, 0.0)
            if now - last_run < self._cooldown:
                logger.info(
                    "memory_stage_skip reason=cooldown chat_id=%s", chat_key
                )
                return 0

        # Gate 2: only messages newer than the last processed run. Messages that
        # have no id (rare synthetic rows) are treated as always-new so they are
        # never silently dropped from memory.
        last_id = type(self)._last_message_id_by_chat.get(chat_key, 0)
        new_messages = [
            message
            for message in recent_messages
            if message.id is None or message.id > last_id
        ]
        if not new_messages:
            logger.info(
                "memory_stage_skip reason=no_new_messages chat_id=%s", chat_key
            )
            return 0
        new_ids = [message.id for message in new_messages if message.id is not None]
        max_new_id = max(new_ids) if new_ids else last_id

        # Gate 3: deterministic prefilter — is there anything worth remembering?
        if self._prefilter_enabled and not should_extract_memory(
            new_messages,
            min_messages=self._prefilter_min_messages,
            min_content_chars=self._prefilter_min_content_chars,
            score_threshold=self._prefilter_score_threshold,
        ):
            logger.info(
                "memory_stage_skip reason=prefilter chat_id=%s new_messages=%s",
                chat_key,
                len(new_messages),
            )
            return 0

        transcript = format_memory_transcript(new_messages)
        try:
            plan = await self._planner.decide(transcript)
        except Exception:
            # Do not advance the watermark on failure: a transient LLM error
            # must not drop these messages from memory permanently.
            logger.exception("memory_plan_failed")
            return 0
        type(self)._last_run_by_chat[chat_key] = time.monotonic()
        type(self)._last_message_id_by_chat[chat_key] = max_new_id
        try:
            written = await self._writer.apply(
                plan,
                source_message_ids=source_message_ids,
                mutation_source="post_reply_extract",
            )
        except Exception:
            logger.exception("memory_apply_failed")
            return 0
        logger.info(
            "memory_stage updates=%s written=%s chat_id=%s new_messages=%s",
            len(plan.updates),
            written,
            chat_key,
            len(new_messages),
        )
        return written
