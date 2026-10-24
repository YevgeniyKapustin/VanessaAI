"""Compose guard: no promise of a later result when no lookup runs.

Only a queued work lookup (``hermes_status == "asked"``) sends a later
message. Any other reply that says «ща гляну… скину» is a false promise:
regenerate it once with a strict note. Fail-open: a failed retry keeps the
first reply.
"""

import logging
from dataclasses import replace

from vanessa.core.generate_request import GenerateRequest
from vanessa.core.protocols import LLMProviderProtocol
from vanessa.core.request_context import get_request_id
from vanessa.pipeline.llm.format.later_promise import promises_later_result

logger = logging.getLogger("vanessa.pipeline.stages")


def is_false_promise(request: GenerateRequest, reply: str) -> bool:
    return request.hermes_status != "asked" and promises_later_result(reply)


async def without_false_promise(
    llm: LLMProviderProtocol, request: GenerateRequest, reply: str
) -> str:
    """Return ``reply``, or a regenerated one when it promised a later result."""
    if not is_false_promise(request, reply):
        return reply
    logger.warning(
        "compose_false_promise request_id=%s hermes=%s",
        get_request_id(),
        request.hermes_status,
    )
    try:
        retried = await llm.generate(replace(request, false_promise_retry=True))
    except Exception:
        logger.exception("compose_false_promise_retry_failed")
        return reply
    if is_false_promise(request, retried):
        logger.warning("compose_false_promise_kept request_id=%s", get_request_id())
    return retried
