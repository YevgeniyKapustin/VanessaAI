"""Prompts for the Hermes follow-up: persona system prompt + data blocks."""

from __future__ import annotations

import re

from services.worker.hermes.payload import HermesAsk
from vanessa.config.channels import load_channel_profile
from vanessa.config.content import AppContent
from vanessa.config.content_hermes import HermesContent
from vanessa.pipeline.llm.prompts.prompt_system import build_system_prompt

_DATA_TAGS = ("user_message", "question_to_hermes", "hermes_answer")
# A data block must not close itself early: strip our own tags from the data.
_DATA_TAG_RE = re.compile(
    r"<\s*/?\s*(?:" + "|".join(_DATA_TAGS) + r")\s*>", re.IGNORECASE
)
_EMPTY = "(empty)"


def build_followup_system_prompt(content: AppContent, channel: str) -> str:
    """Vanessa's compose system prompt for one plain message.

    Stickers and ``[next]`` blocks are off: the outbound path posts the
    text as one message.
    """
    profile = load_channel_profile(channel).model_copy(
        update={"stickers": False, "split_messages": False}
    )
    return build_system_prompt(content, profile)


def _block(tag: str, text: str) -> str:
    body = _DATA_TAG_RE.sub("", text).strip() or _EMPTY
    return f"<{tag}>\n{body}\n</{tag}>"


def build_followup_user_prompt(
    ask: HermesAsk, answer: str | None, prompts: HermesContent
) -> str:
    """Data blocks first, then the data rules, then the task (last)."""
    parts = [
        _block("user_message", ask.user_message),
        _block("question_to_hermes", ask.question),
    ]
    if answer:
        parts.append(_block("hermes_answer", answer))
    task = prompts.answered_task if answer else prompts.undelivered_task
    parts.extend([prompts.data_rules.strip(), task.strip()])
    return "\n\n".join(parts)
