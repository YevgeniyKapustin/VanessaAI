import asyncio
from contextlib import nullcontext
from typing import Any

from vanessa.config.settings import settings
from vanessa.infrastructure.observability import tracing
from vanessa.infrastructure.observability.tracing import (
    LangfuseTracer,
    NullTracer,
    get_tracer,
    hash_identifier,
    reset_tracer,
    set_tracer,
)


def _noop_propagator(**kwargs: Any) -> Any:
    """Stand-in for langfuse.propagate_attributes used in unit tests."""
    del kwargs
    return nullcontext()


class _FakeObservation:
    def __init__(self, kind: str, sink: list[dict[str, Any]]) -> None:
        self.kind = kind
        self._sink = sink
        self._record: dict[str, Any] = {"kind": kind, "obs": self}
        self._sink.append(self._record)
        self.ended = False

    def _with(self, kwargs: dict[str, Any]):
        self._record["kwargs"] = kwargs
        return self

    def update(self, **kwargs: Any) -> None:
        self._record["updated"] = kwargs

    def end(self) -> None:
        self.ended = True


class _FakeObservationCM:
    """Sync context manager that yields a fake observation and ends it on exit."""

    def __init__(self, obs: _FakeObservation) -> None:
        self._obs = obs

    def __enter__(self) -> _FakeObservation:
        return self._obs

    def __exit__(self, *exc: Any) -> bool:
        self._obs.end()
        return False


class _FakeClient:
    def __init__(self) -> None:
        self.sink: list[dict[str, Any]] = []
        self.traces: list[_FakeObservation] = []
        self.flushed = False
        self._seq = 0

    def create_trace_id(self, *, seed: str | None = None) -> str:
        del seed
        self._seq += 1
        return f"trace-{self._seq}"

    def start_as_current_observation(
        self,
        *,
        trace_context: dict[str, Any] | None = None,
        name: str,
        as_type: str = "span",
        **kwargs: Any,
    ) -> _FakeObservationCM:
        obs = _FakeObservation(as_type, self.sink)._with({**kwargs, "name": name})
        # Root observations (explicit trace id, no parent) form the trace.
        if trace_context is not None and "parent_span_id" not in trace_context:
            self.traces.append(obs)
        return _FakeObservationCM(obs)

    def flush(self) -> None:
        self.flushed = True


def test_hash_identifier_stable_and_private() -> None:
    a = hash_identifier(123, salt="s")
    b = hash_identifier(123, salt="s")
    assert a == b
    assert len(a) == 16
    assert "123" not in a
    assert hash_identifier(None) == "anonymous"


def test_null_tracer_is_noop() -> None:
    tracer = NullTracer()
    assert tracer.enabled is False

    async def run() -> str:
        async with tracer.trace(name="pipeline", user_id="u"):
            async with tracer.span(name="gate"):
                async with tracer.generation(name="llm", model="m", input="q", output="a"):
                    return "ok"

    assert asyncio.run(run()) == "ok"


def test_langfuse_tracer_creates_nested_observations(monkeypatch) -> None:
    monkeypatch.setattr(tracing, "_propagate_attributes", _noop_propagator)
    client = _FakeClient()
    tracer = LangfuseTracer(client=client)

    async def run() -> None:
        async with tracer.trace(name="pipeline", user_id="u1", session_id="chat1"):
            async with tracer.span(name="gate"):
                async with tracer.generation(
                    name="llm_generation",
                    model="m",
                    input="q",
                    output="a",
                    usage={"input": 1, "output": 2},
                ) as gen:
                    gen.update(metadata={"ok": True})

    asyncio.run(run())
    assert len(client.traces) == 1
    # The trace root is a v4 "chain" observation carrying user/session attrs.
    root = client.traces[0]
    assert root._record["kind"] == "chain"
    assert root._record["kwargs"]["name"] == "pipeline"
    # Nested span + generation must have been created and ended on exit.
    records = {rec["kind"]: rec for rec in client.sink}
    assert "span" in records
    assert "generation" in records
    assert records["generation"]["obs"].ended is True
    assert records["span"]["obs"].ended is True
    assert records["generation"]["kwargs"]["model"] == "m"
    # v2-era ``usage`` maps to v4 ``usage_details``.
    assert records["generation"]["kwargs"]["usage_details"] == {"input": 1, "output": 2}
    assert records["generation"]["updated"] == {"metadata": {"ok": True}}
    assert client.flushed is True


def test_langfuse_tracer_update_translates_usage(monkeypatch) -> None:
    monkeypatch.setattr(tracing, "_propagate_attributes", _noop_propagator)
    client = _FakeClient()
    tracer = LangfuseTracer(client=client)

    async def run() -> None:
        async with tracer.trace(name="pipeline"):
            async with tracer.generation(name="llm", model="m") as gen:
                gen.update(output="hi", usage={"input": 3, "output": 4})

    asyncio.run(run())
    gen = next(rec for rec in client.sink if rec["kind"] == "generation")
    assert gen["updated"] == {
        "output": "hi",
        "usage_details": {"input": 3, "output": 4},
    }


def test_langfuse_tracer_unsampled_emits_nothing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "langfuse_sample_rate", 0.0)
    client = _FakeClient()
    tracer = LangfuseTracer(client=client)

    async def run() -> None:
        async with tracer.trace(name="pipeline"):
            async with tracer.span(name="gate"):
                pass

    asyncio.run(run())
    assert client.sink == []
    assert client.traces == []


def test_langfuse_tracer_sample_rate_one_traces(monkeypatch) -> None:
    monkeypatch.setattr(settings, "langfuse_sample_rate", 1.0)
    monkeypatch.setattr(tracing, "_propagate_attributes", _noop_propagator)
    client = _FakeClient()
    tracer = LangfuseTracer(client=client)

    async def run() -> None:
        async with tracer.trace(name="pipeline"):
            async with tracer.span(name="gate"):
                pass

    asyncio.run(run())
    assert len(client.traces) == 1


def test_set_and_reset_tracer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    set_tracer(NullTracer())
    try:
        assert isinstance(get_tracer(), NullTracer)
    finally:
        reset_tracer()
