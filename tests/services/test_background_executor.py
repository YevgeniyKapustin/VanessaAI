import asyncio

import pytest

from vanessa.services.background import BackgroundExecutor


@pytest.mark.asyncio
async def test_submit_runs_jobs_in_order():
    executor = BackgroundExecutor(maxsize=10, workers=1)
    executor.start()
    results: list[str] = []

    async def job_a() -> None:
        results.append("a")

    async def job_b() -> None:
        results.append("b")

    executor.submit(job_a)
    executor.submit(job_b)
    await executor.join()
    await executor.shutdown()

    assert results == ["a", "b"]


@pytest.mark.asyncio
async def test_submit_before_start_drops_job():
    executor = BackgroundExecutor(maxsize=10, workers=1)
    ran: list[bool] = []

    async def job() -> None:
        ran.append(True)

    executor.submit(job)  # not started -> dropped, never blocks
    await asyncio.sleep(0.05)

    assert ran == []
    await executor.shutdown()


@pytest.mark.asyncio
async def test_queue_full_drops_job():
    executor = BackgroundExecutor(maxsize=1, workers=1)
    executor.start()
    started = asyncio.Event()
    release = asyncio.Event()
    ran: list[str] = []

    async def blocking() -> None:
        ran.append("blocking")
        started.set()
        await release.wait()
        ran.append("done")

    async def fast() -> None:
        ran.append("fast")

    executor.submit(blocking)
    await started.wait()  # worker picked up the blocking job
    executor.submit(fast)  # queued (one free slot)
    executor.submit(fast)  # queue full -> dropped
    await asyncio.sleep(0.05)
    release.set()
    await executor.join()
    await executor.shutdown()

    assert ran.count("fast") == 1
    assert ran.count("blocking") == 1
    assert ran.count("done") == 1


@pytest.mark.asyncio
async def test_job_exception_is_swallowed():
    executor = BackgroundExecutor(maxsize=10, workers=1)
    executor.start()
    ran: list[str] = []

    async def boom() -> None:
        ran.append("boom")
        raise RuntimeError("nope")

    async def after() -> None:
        ran.append("after")

    executor.submit(boom)
    executor.submit(after)
    await executor.join()
    await executor.shutdown()

    assert ran == ["boom", "after"]


@pytest.mark.asyncio
async def test_shutdown_cancels_workers():
    executor = BackgroundExecutor(maxsize=10, workers=2)
    executor.start()
    await executor.shutdown()

    assert executor._workers == []
    assert executor._started is False
