from vanessa.infrastructure.hermes import (
    HermesRun,
    HermesUnavailableError,
    wait_for_output,
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


async def _no_sleep(_seconds: float) -> None:
    return None


def _run(status: str, output: str = "") -> HermesRun:
    return HermesRun(run_id="run_1", status=status, output=output)


async def _wait(client, *, clock=lambda: 0.0, max_wait=60.0):
    return await wait_for_output(
        client,
        "run_1",
        poll_seconds=1.0,
        max_wait_seconds=max_wait,
        sleep=_no_sleep,
        clock=clock,
    )


async def test_returns_output_after_running():
    client = _FakeClient([_run("running"), _run("completed", "3 open MRs")])

    assert await _wait(client) == "3 open MRs"
    assert client.stopped == []


async def test_failed_run_returns_none():
    client = _FakeClient([_run("failed")])

    assert await _wait(client) is None


async def test_completed_without_output_returns_none():
    client = _FakeClient([_run("completed", "")])

    assert await _wait(client) is None


async def test_approval_wait_stops_run():
    client = _FakeClient([_run("waiting_for_approval")])

    assert await _wait(client) is None
    assert client.stopped == ["run_1"]


async def test_deadline_stops_run_even_if_stop_fails():
    ticks = iter([0.0, 100.0])
    client = _FakeClient([_run("running")], stop_fails=True)

    assert await _wait(client, clock=lambda: next(ticks), max_wait=10.0) is None
    assert client.stopped == ["run_1"]
