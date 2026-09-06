"""Retry loop, tracing span, and error mapping for provider completions."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from vanessa.infrastructure.observability.metrics import (
    classify_llm_error,
    record_llm_call,
)

type CompletionFn = Callable[[Any, float], Awaitable[str]]
type RetryFn = Callable[[Exception], bool]
type SleepFn = Callable[[float], Awaitable[None]]


def _record_completion_error(
    *,
    provider: str,
    model: str,
    started: float,
    exc: Exception,
) -> None:
    record_llm_call(
        provider=provider,
        model=model,
        kind="generation",
        started=started,
        status="error",
        error_type=classify_llm_error(exc),
    )


async def _sleep_if_retryable(
    exc: Exception,
    *,
    attempt: int,
    max_retries: int,
    should_retry: RetryFn,
    sleep: SleepFn,
    logger: logging.Logger,
) -> bool:
    if attempt >= max_retries or not should_retry(exc):
        return False
    delay = 1.0 * (attempt + 1)
    logger.warning(
        "LLM request failed (attempt %s/%s), retry in %.1fs: %s",
        attempt + 1,
        max_retries + 1,
        delay,
        exc,
    )
    await sleep(delay)
    return True


async def _retry_until_success(
    gen: Any,
    complete: CompletionFn,
    *,
    provider: str,
    model: str,
    max_retries: int,
    should_retry: RetryFn,
    sleep: SleepFn,
    logger: logging.Logger,
) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        started = time.perf_counter()
        try:
            return await complete(gen, started)
        except Exception as exc:
            last_error = exc
            _record_completion_error(
                provider=provider,
                model=model,
                started=started,
                exc=exc,
            )
            if not await _sleep_if_retryable(
                exc,
                attempt=attempt,
                max_retries=max_retries,
                should_retry=should_retry,
                sleep=sleep,
                logger=logger,
            ):
                raise
    assert last_error is not None
    raise last_error


async def run_completion_with_retries(
    generation_cm: AbstractAsyncContextManager[Any],
    complete: CompletionFn,
    *,
    provider: str,
    model: str,
    max_retries: int,
    should_retry: RetryFn,
    sleep: SleepFn,
    logger: logging.Logger,
) -> str:
    async with generation_cm as gen:
        return await _retry_until_success(
            gen,
            complete,
            provider=provider,
            model=model,
            max_retries=max_retries,
            should_retry=should_retry,
            sleep=sleep,
            logger=logger,
        )
