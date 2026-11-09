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


def failure_note(prompts: HermesContent, reason: str) -> str:
    """The reason block for a run that brought nothing back.

    Empty when the code has no meaning in ``failure_meanings``: a made-up
    reason is worse than the generic "did not deliver" line.
    """
    meaning = prompts.failure_meanings.get(reason, "").strip()
    template = prompts.failure_note.strip()
    if not (reason and meaning and template):
        return ""
    return (
        template.replace("{reason}", reason)
        .replace("{meaning}", meaning)
        .strip()
    )


def _task(
    prompts: HermesContent, ask: HermesAsk, *, answered: bool, named_reason: bool
) -> str:
    """The closing task: agents get a one-message answer, never a thread."""
    if not answered:
        return _undelivered_task(prompts, named_reason=named_reason)
    return _answered_task(prompts, ask)


def _undelivered_task(prompts: HermesContent, *, named_reason: bool) -> str:
    if named_reason and prompts.undelivered_reason_task.strip():
        return prompts.undelivered_reason_task
    return prompts.undelivered_task


def _answered_task(prompts: HermesContent, ask: HermesAsk) -> str:
    if ask.proxy:
        return prompts.proxy_answered_task or prompts.answered_task
    return _agent_or_plain(prompts, bot_peer=ask.bot_peer)


def _agent_or_plain(prompts: HermesContent, *, bot_peer: bool) -> str:
    if bot_peer:
        return prompts.agent_answered_task or prompts.answered_task
    return prompts.answered_task


def _timing(prompts: HermesContent, elapsed_seconds: float | None) -> str:
    template = prompts.timing_note.strip()
    if not template or elapsed_seconds is None:
        return ""
    return template.replace("{duration}", format_duration(elapsed_seconds))


def build_followup_user_prompt(
    ask: HermesAsk,
    answer: str | None,
    prompts: HermesContent,
    *,
    file_task: str = "",
    elapsed_seconds: float | None = None,
    failure_reason: str = "",
) -> str:
    """Data blocks first, then the data rules, then the task (last).

    ``file_task`` (the HTML file note) goes right before the main task,
    so the "[answer]" instruction stays last. ``elapsed_seconds`` fills the
    timing note: the model gets the real run time, not a guess.
    ``failure_reason`` names why a run brought nothing back.
    """
    parts = [
        _block("user_message", ask.user_message),
        _block("question_to_hermes", ask.question),
    ]
    parts.extend(_body(prompts, answer, file_task, elapsed_seconds, failure_reason))
    named_reason = bool(failure_note(prompts, failure_reason))
    task = _task(prompts, ask, answered=bool(answer), named_reason=named_reason)
    parts.append(task.strip())
    return "\n\n".join(parts)


def _body(
    prompts: HermesContent,
    answer: str | None,
    file_task: str,
    elapsed_seconds: float | None,
    failure_reason: str,
) -> list[str]:
    """The answer, the rules, the timing, the reason, the file note."""
    blocks = [
        text
        for text in (
            prompts.data_rules.strip(),
            _timing(prompts, elapsed_seconds),
            failure_note(prompts, failure_reason),
            file_task.strip(),
        )
        if text
    ]
    if answer:
        blocks.insert(0, _block("hermes_answer", answer))
    return blocks
