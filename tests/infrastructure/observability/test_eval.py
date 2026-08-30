import asyncio
import json

from vanessa.config.settings import settings
from vanessa.infrastructure.observability.eval import RagTriadEvaluator


class _FakeCompleter:
    def __init__(self, raw: str | None = None, error: Exception | None = None) -> None:
        self._raw = raw
        self._error = error
        self.calls: list[tuple[str, str, dict]] = []

    async def complete(self, model: str, messages: list[dict], *, kind: str = "completion", **kwargs):
        self.calls.append((model, kind, kwargs))
        if self._error is not None:
            raise self._error
        return self._raw or ""


def _run(coro):
    return asyncio.run(coro)


def test_evaluate_records_scores() -> None:
    raw = json.dumps(
        {
            "context_relevance": 0.8,
            "groundedness": 0.9,
            "answer_relevance": 0.7,
            "reasons": {},
        }
    )
    completer = _FakeCompleter(raw=raw)
    evaluator = RagTriadEvaluator(
        completer=completer, model="judge", enabled=True, sample_rate=1.0
    )
    scores = _run(
        evaluator.evaluate(question="q", answer="a", context="ctx")
    )
    assert scores == {"context_relevance": 0.8, "groundedness": 0.9, "answer_relevance": 0.7}
    assert completer.calls[0][1] == "eval"
    assert completer.calls[0][2]["temperature"] == 0.0


def test_evaluate_clamps_out_of_range_scores() -> None:
    raw = json.dumps(
        {"context_relevance": 2.5, "groundedness": -1.0, "answer_relevance": 0.4}
    )
    evaluator = RagTriadEvaluator(
        completer=_FakeCompleter(raw=raw), enabled=True, sample_rate=1.0
    )
    scores = _run(evaluator.evaluate(question="q", answer="a", context="ctx"))
    assert scores["context_relevance"] == 1.0
    assert scores["groundedness"] == 0.0
    assert scores["answer_relevance"] == 0.4


def test_evaluate_fails_open_on_judge_error() -> None:
    evaluator = RagTriadEvaluator(
        completer=_FakeCompleter(error=RuntimeError("provider down")),
        enabled=True,
        sample_rate=1.0,
    )
    scores = _run(evaluator.evaluate(question="q", answer="a", context="ctx"))
    assert scores == {}


def test_evaluate_fails_open_on_unparseable() -> None:
    evaluator = RagTriadEvaluator(
        completer=_FakeCompleter(raw="not json at all"),
        enabled=True,
        sample_rate=1.0,
    )
    scores = _run(evaluator.evaluate(question="q", answer="a", context="ctx"))
    assert scores == {}


def test_should_run_respects_feature_and_sampling(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_eval_enabled", False)
    assert RagTriadEvaluator().should_run() is False

    monkeypatch.setattr(settings, "rag_eval_enabled", True)
    monkeypatch.setattr(settings, "rag_eval_sample_rate", 0.0)
    assert RagTriadEvaluator().should_run() is False

    monkeypatch.setattr(settings, "rag_eval_sample_rate", 1.0)
    assert RagTriadEvaluator().should_run() is True
