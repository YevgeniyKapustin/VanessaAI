"""Require an explicit final-answer boundary before delivering compose output.

A separate provider reasoning field does not guarantee that message content
contains the answer. Never infer this from wording: retry untagged content
once, then reject it with ``UntaggedReplyError``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from vanessa.pipeline.llm.format.answer_tag import extract_answer, is_untagged_reply

UNTAGGED_ATTEMPTS = 2

logger = logging.getLogger("vanessa.pipeline.llm.tagged_reply")


class UntaggedReplyError(Exception):
    """The output had no final-answer boundary after every attempt."""

    def __init__(self, model: str) -> None:
        super().__init__(f"untagged reply from {model}")
        self.model = model


async def request_tagged(
    create: Callable[..., Awaitable[Any]],
    text_of: Callable[[Any], str],
    *,
    model: str,
) -> Any:
    """Retry untagged output once; return the last response.

    ``create(strict=...)`` gets ``strict=True`` on a retry, so the caller can add
    a note that demands the tag.
    """
    for attempt in range(1, UNTAGGED_ATTEMPTS):
        response = await create(strict=False)
        text = text_of(response)
        if not is_untagged_reply(text):
            return response
        logger.warning(
            "llm_untagged_retry model=%s attempt=%s chars=%s",
            model,
            attempt,
            len(text),
        )
    return await create(strict=True)


def split_reply(text: str, model: str) -> tuple[str, str]:
    """``(reply, reasoning)``; empty reply for any untagged output."""
    if is_untagged_reply(text):
        logger.warning("llm_untagged_silenced model=%s chars=%s", model, len(text))
        return "", ""
    return extract_answer(text)


def raise_if_untagged(text: str, model: str) -> None:
    """Raise ``UntaggedReplyError`` when the final output has no answer boundary."""
    if is_untagged_reply(text):
        raise UntaggedReplyError(model)
