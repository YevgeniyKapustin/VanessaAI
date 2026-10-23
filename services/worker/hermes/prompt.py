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
# Under this, the run time is given in seconds; from it, in minutes.
SECONDS_LIMIT = 90


def build_followup_system_prompt(content: AppContent, channel: str) -> str:
    """Vanessa's compose system prompt for the follow-up.

    Stickers are off. ``[next]`` blocks follow the channel profile, as in
    her normal replies: the outbound path posts each block as a message.
    """
    profile = load_channel_profile(channel).model_copy(update={"stickers": False})
    return build_system_prompt(content, profile)


def format_duration(seconds: float) -> str:
    """«16 seconds» under 90 s, else whole minutes («3 minutes»)."""
    if seconds < SECONDS_LIMIT:
        whole = max(1, round(seconds))
        return "1 second" if whole == 1 else f"{whole} seconds"
    return f"{round(seconds / 60)} minutes"


def _block(tag: str, text: str) -> str:
    body = _DATA_TAG_RE.sub("", text).strip() or _EMPTY
    return f"<{tag}>\n{body}\n</{tag}>"


def build_followup_user_prompt(
    ask: HermesAsk,
    answer: str | None,
    prompts: HermesContent,
    *,
    file_task: str = "",
    elapsed_seconds: float | None = None,
) -> str:
    """Data blocks first, then the data rules, then the task (last).

    ``file_task`` (the HTML file note) goes right before the main task,
    so the "[answer]" instruction stays last. ``elapsed_seconds`` fills the
    timing note: the model gets the real run time, not a guess.
    """
    parts = [
        _block("user_message", ask.user_message),
        _block("question_to_hermes", ask.question),
    ]
    if answer:
        parts.append(_block("hermes_answer", answer))
    parts.append(prompts.data_rules.strip())
    timing = prompts.timing_note.strip()
    if timing and elapsed_seconds is not None:
        parts.append(timing.replace("{duration}", format_duration(elapsed_seconds)))
    if file_task.strip():
        parts.append(file_task.strip())
    task = prompts.answered_task if answer else prompts.undelivered_task
    parts.append(task.strip())
    return "\n\n".join(parts)
