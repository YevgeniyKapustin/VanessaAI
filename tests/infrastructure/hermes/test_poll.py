from vanessa.infrastructure.hermes import (
    HermesRun,
    HermesUnavailableError,
    HermesWaitResult,
    wait_for_output,
)
from vanessa.infrastructure.hermes.models import (
    FAILURE_BLOCKED,
    FAILURE_EMPTY,
    FAILURE_FAILED,
    FAILURE_INTERRUPTED,
    FAILURE_TIMEOUT,
)


class _FakeClient:
    def __init__(self, statuses: list[HermesRun], *, stop_fails: bool = False) -> None:
        self._statuses = statuses
        self._stop_fails = stop_fails
        self.stopped: list[str] = []

    async def get_run(self, run_id: str) -> HermesRun:
        assert run_id == "run_1"
        return self._statuses.pop(0)

    async def stop_run(self, run_id: str) -> None:
        self.stopped.append(run_id)
        if self._stop_fails:
            raise HermesUnavailableError("down")


class _Ticking:
    """A clock that moves 5 s per call: started at 5, so progress can fire."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 5.0
        return self.now


async def _no_sleep(_seconds: float) -> None:
    return None


def _run(status: str, output: str = "") -> HermesRun:
    return HermesRun(run_id="run_1", status=status, output=output)


async def _wait(client, *, clock=lambda: 0.0, max_wait=60.0, progress=None):
    return await wait_for_output(
        client,
        "run_1",
        poll_seconds=1.0,
        max_wait_seconds=max_wait,
        progress_after_seconds=10.0,
        on_progress=progress,
        sleep=_no_sleep,
        clock=clock,
    )


async def test_returns_output_after_running():
    client = _FakeClient([_run("running"), _run("completed", "3 open MRs")])

    result = await _wait(client)

    assert result == HermesWaitResult(answer="3 open MRs")
    assert client.stopped == []


async def test_failed_run_reports_failed():
    client = _FakeClient([_run("failed")])

    result = await _wait(client)

    assert result.answer is None
    assert result.failure == FAILURE_FAILED


async def test_cancelled_run_reports_interrupted():
    client = _FakeClient([_run("cancelled")])

    assert (await _wait(client)).failure == FAILURE_INTERRUPTED


async def test_completed_without_output_reports_empty():
    client = _FakeClient([_run("completed", "")])

    assert (await _wait(client)).failure == FAILURE_EMPTY


async def test_approval_wait_stops_run_and_reports_blocked():
    client = _FakeClient([_run("waiting_for_approval")])

    result = await _wait(client)

    assert result.answer is None
    assert result.failure == FAILURE_BLOCKED
    assert client.stopped == ["run_1"]


async def test_deadline_stops_run_even_if_stop_fails():
    ticks = iter([0.0, 100.0])
    client = _FakeClient([_run("running")], stop_fails=True)

    result = await _wait(client, clock=lambda: next(ticks), max_wait=10.0)

    assert result.failure == FAILURE_TIMEOUT
    assert client.stopped == ["run_1"]


async def test_progress_fires_once_while_the_run_is_long():
    clock = _Ticking()
    told: list[float] = []

    async def on_progress() -> None:
        told.append(clock.now)

    client = _FakeClient(
        [_run("running"), _run("running"), _run("running"), _run("completed", "ok")]
    )

    result = await _wait(client, clock=clock, max_wait=120.0, progress=on_progress)

    assert result.answer == "ok"
    assert len(told) == 1


async def test_progress_does_not_fire_before_the_threshold():
    told: list[int] = []

    async def on_progress() -> None:
        told.append(1)

    ticks = iter([0.0, 5.0, 9.0, 9.0])
    client = _FakeClient(
        [_run("running"), _run("running"), _run("completed", "ok")]
    )

    await _wait(client, clock=lambda: next(ticks), progress=on_progress)

    assert told == []


async def test_progress_is_off_without_a_callback():
    ticks = iter([0.0, 50.0])
    client = _FakeClient([_run("running"), _run("completed", "ok")])

    result = await _wait(client, clock=lambda: next(ticks))

    assert result.answer == "ok"
