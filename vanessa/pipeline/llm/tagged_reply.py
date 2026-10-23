"""Guard against untagged compose output: text without ``[answer]``.

The composer writes reasoning, then ``[answer]``, then the message. Output
without the tag can be the reasoning alone («Он просто зовёт… Отвечаю
сухо»): sending it leaks the reasoning into the chat. Ask once more with a
strict note, then report the output as untagged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from vanessa.pipeline.llm.format.answer_tag import extract_answer, is_untagged_reply

UNTAGGED_ATTEMPTS = 2

logger = logging.getLogger("vanessa.pipeline.llm.tagged_reply")


class UntaggedReplyError(Exception):
    """The model output had no ``[answer]`` tag after every attempt."""

    def __init__(self, model: str) -> None:
        super().__init__(f"untagged reply from {model}")
        self.model = model


async def request_tagged(
    create: Callable[..., Awaitable[Any]],
    text_of: Callable[[Any], str],
    *,
    model: str,
) -> Any:
    """Call ``create`` again while its output is untagged; return the last response.

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
    """``(reply, reasoning)``; empty reply for output that is still untagged."""
    if is_untagged_reply(text):
        logger.warning("llm_untagged_silenced model=%s output=%r", model, text)
        return "", ""
    return extract_answer(text)


def raise_if_untagged(text: str, model: str) -> None:
    """Raise ``UntaggedReplyError`` when the final output has no tag."""
    if is_untagged_reply(text):
        raise UntaggedReplyError(model)
