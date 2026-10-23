"""Guard against untagged compose output: bare reasoning without ``[answer]``.

The composer writes reasoning, then ``[answer]``, then the message. Output
without the tag is usually the reasoning alone («Он просто зовёт… Отвечаю
сухо»): sending it leaks the reasoning into the chat. Ask once more, then
stay silent.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from vanessa.pipeline.llm.format.answer_tag import extract_answer, is_untagged_reply

UNTAGGED_ATTEMPTS = 2

logger = logging.getLogger("vanessa.pipeline.llm.tagged_reply")


async def request_tagged(
    create: Callable[[], Awaitable[Any]],
    text_of: Callable[[Any], str],
    *,
    model: str,
) -> Any:
    """Call ``create`` again while its output is untagged; return the last response."""
    for attempt in range(1, UNTAGGED_ATTEMPTS):
        response = await create()
        text = text_of(response)
        if not is_untagged_reply(text):
            return response
        logger.warning(
            "llm_untagged_retry model=%s attempt=%s chars=%s",
            model,
            attempt,
            len(text),
        )
    return await create()


def split_reply(text: str, model: str) -> tuple[str, str]:
    """``(reply, reasoning)``; empty reply for output that is still untagged."""
    if is_untagged_reply(text):
        logger.warning("llm_untagged_silenced model=%s output=%r", model, text)
        return "", ""
    return extract_answer(text)
