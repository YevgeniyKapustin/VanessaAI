"""Guard against leaked reasoning in compose output.

The composer writes reasoning, then ``[answer]``, then the message. Output
without the tag is usually the clean message (thinking mode returns the
reasoning in a separate field): it is the answer. Untagged output that reads
as reasoning («Он просто зовёт… Отвечаю сухо») would leak into the chat:
ask once more with a strict note, then report it (``UntaggedReplyError``).
See ``format.reasoning_leak``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from vanessa.pipeline.llm.format.answer_tag import extract_answer, is_untagged_reply
from vanessa.pipeline.llm.format.reasoning_leak import is_reasoning_leak

UNTAGGED_ATTEMPTS = 2

logger = logging.getLogger("vanessa.pipeline.llm.tagged_reply")


class UntaggedReplyError(Exception):
    """The output was untagged reasoning after every attempt."""

    def __init__(self, model: str) -> None:
        super().__init__(f"untagged reply from {model}")
        self.model = model


async def request_tagged(
    create: Callable[..., Awaitable[Any]],
    text_of: Callable[[Any], str],
    *,
    model: str,
) -> Any:
    """Call ``create`` again while its output is leaked reasoning; return the last.

    ``create(strict=...)`` gets ``strict=True`` on a retry, so the caller can add
    a note that demands the tag.
    """
    for attempt in range(1, UNTAGGED_ATTEMPTS):
        response = await create(strict=False)
        text = text_of(response)
        if not is_reasoning_leak(text):
            return response
        logger.warning(
            "llm_untagged_retry model=%s attempt=%s chars=%s",
            model,
            attempt,
            len(text),
        )
    return await create(strict=True)


def split_reply(text: str, model: str) -> tuple[str, str]:
    """``(reply, reasoning)``; empty reply for leaked reasoning."""
    if is_reasoning_leak(text):
        logger.warning("llm_untagged_silenced model=%s output=%r", model, text)
        return "", ""
    if is_untagged_reply(text):
        logger.info("llm_untagged_accepted model=%s chars=%s", model, len(text))
    return extract_answer(text)


def raise_if_untagged(text: str, model: str) -> None:
    """Raise ``UntaggedReplyError`` when the final output is leaked reasoning."""
    if is_reasoning_leak(text):
        raise UntaggedReplyError(model)
