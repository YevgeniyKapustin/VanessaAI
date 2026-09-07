from types import SimpleNamespace
from unittest.mock import AsyncMock

from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    StoredMessage,
)
from vanessa.core.turn import ChatTurnInput
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.orchestrator.post_reply import _PostReplyMixin


class _Harness(_PostReplyMixin):
    def __init__(self, **kwargs) -> None:
        self._memory = kwargs.get("memory")
        self._metrics = kwargs.get("metrics")
        self._background = kwargs.get("background")
        self._dispatcher = kwargs.get("dispatcher")
        self._eval = kwargs.get("eval")
        self._photo_captioner = kwargs.get("photo_captioner")
        self._session_factory = kwargs.get("session_factory")
        self._messages = kwargs.get("messages")


class _BG:
    def __init__(self) -> None:
        self.jobs: list = []

    def submit(self, job) -> None:
        self.jobs.append(job)


class _MetricsSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a) -> bool:
        return False


class _Disp:
    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, kind, payload, **kwargs) -> None:
        self.submitted.append((kind, payload, kwargs))


def _ctx(*, with_photo: bool = False, sender_id: int | None = 3) -> TurnPipelineContext:
    attachments = [{"data_url": "data:image/jpeg;base64,AA"}] if with_photo else None
    ctx = TurnPipelineContext(
        turn=ChatTurnInput(
            telegram_chat_id=-100,
            message="hi",
            sender_telegram_id=sender_id,
        )
    )
    ctx.user_msg = StoredMessage(
        id=9,
        role="user",
        content="hi",
        sender_telegram_id=sender_id,
        attachments=attachments,
    )
    ctx.recent = [
        ContextMessage(id=9, role="user", content="hi", sender_telegram_id=sender_id)
    ]
    ctx.reply = "pong"
    ctx.knowledge_blocks = [
        KnowledgeBlock(title="t", path="p", kind="person", content="k")
    ]
    ctx.context_blocks = [
        ContextBlock(
            anchor_id=9,
            messages=(ContextMessage(id=9, role="user", content="ctx"),),
        )
    ]
    ctx.humor_quotes = ["quote"]
    return ctx


async def test_inline_post_reply_runs_memory_metrics_caption(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.post_reply_jobs.settings.vision_photo_caption_enabled",
        True,
    )
    memory = SimpleNamespace(run=AsyncMock(return_value=1))
    metrics = SimpleNamespace(run=AsyncMock(return_value=1))
    captioner = SimpleNamespace(generate=AsyncMock(return_value="cat"))
    messages = SimpleNamespace(update_photo_caption=AsyncMock())
    harness = _Harness(
        memory=memory,
        metrics=metrics,
        photo_captioner=captioner,
        messages=messages,
    )
    await harness._run_post_reply(_ctx(with_photo=True))
    memory.run.assert_awaited()
    metrics.run.assert_awaited()
    messages.update_photo_caption.assert_awaited()


async def test_inline_swallows_memory_and_metrics_errors() -> None:
    memory = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("m")))
    metrics = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("x")))
    harness = _Harness(memory=memory, metrics=metrics, messages=SimpleNamespace())
    await harness._run_post_reply(_ctx())


async def test_background_and_dispatcher_post_reply(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.post_reply_jobs.settings.vision_photo_caption_enabled",
        True,
    )
    bg = _BG()
    evaler = SimpleNamespace(should_run=lambda: True, evaluate=AsyncMock())
    harness = _Harness(
        memory=SimpleNamespace(run=AsyncMock()),
        metrics=SimpleNamespace(run=AsyncMock()),
        background=bg,
        eval=evaler,
        photo_captioner=SimpleNamespace(generate=AsyncMock(return_value="c")),
        messages=SimpleNamespace(update_photo_caption=AsyncMock()),
    )
    await harness._run_post_reply(_ctx(with_photo=True))
    assert bg.jobs
    for job in bg.jobs:
        await job()

    disp = _Disp()
    dispatched = _Harness(
        dispatcher=disp,
        background=bg,
        eval=evaler,
        photo_captioner=SimpleNamespace(),
        messages=SimpleNamespace(),
    )
    await dispatched._run_post_reply(_ctx(with_photo=True))
    kinds = [item[0] for item in disp.submitted]
    assert kinds


async def test_metrics_job_uses_session_factory() -> None:
    calls: list = []

    class Metrics:
        async def run(self, _repo, **kwargs) -> int:
            calls.append(kwargs)
            return 1

    harness = _Harness(
        metrics=Metrics(),
        session_factory=_MetricsSession,
    )
    job = harness._build_metrics_job(_ctx())
    assert job is not None
    await job()
    assert calls
    assert harness._build_metrics_job(_ctx(sender_id=None)) is None


async def test_eval_job_and_caption_skips(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.post_reply_jobs.settings.vision_photo_caption_enabled",
        False,
    )
    evaler = SimpleNamespace(evaluate=AsyncMock(side_effect=RuntimeError("e")))
    harness = _Harness(eval=evaler)
    job = harness._build_eval_job(_ctx())
    await job()
    assert harness._build_photo_caption_job(_ctx(with_photo=True)) is None
    harness._photo_captioner = SimpleNamespace(generate=AsyncMock(return_value=""))
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.post_reply_jobs.settings.vision_photo_caption_enabled",
        True,
    )
    caption_job = harness._build_photo_caption_job(_ctx(with_photo=True))
    assert caption_job is not None
    await caption_job()
    empty = harness._photo_caption_target(
        TurnPipelineContext(
            turn=ChatTurnInput(telegram_chat_id=1, message="x", sender_telegram_id=1)
        )
    )
    assert empty is None
