from vanessa.core.messages import ContextMessage
from vanessa.knowledge.memory.memory_planner import MemoryPlanner
from vanessa.knowledge.memory.memory_stage import MemoryStage
from vanessa.knowledge.schema import MemoryPlan


class _Planner:
    def __init__(self, plan: MemoryPlan | None = None, *, error: bool = False) -> None:
        self.plan = plan or MemoryPlan(updates=({"type": "quote"},))
        self.error = error
        self.calls = 0

    async def decide(self, transcript: str) -> MemoryPlan:
        del transcript
        self.calls += 1
        if self.error:
            raise RuntimeError("llm")
        return self.plan


_WRITTEN = 2


class _Writer:
    def __init__(self, *, error: bool = False) -> None:
        self.error = error
        self.calls = 0

    async def apply(self, plan, **kwargs) -> int:
        del plan, kwargs
        self.calls += 1
        if self.error:
            raise RuntimeError("vault")
        return _WRITTEN


def _msg(msg_id: int, content: str = "fact about work and life " * 5) -> ContextMessage:
    return ContextMessage(
        id=msg_id,
        role="user",
        content=content,
        sender_telegram_id=1,
        sender_name="Ada",
    )


def _stage(planner=None, writer=None, **kwargs) -> MemoryStage:
    MemoryStage._last_run_by_chat.clear()
    MemoryStage._last_message_id_by_chat.clear()
    options = {"cooldown_seconds": 0, "prefilter_enabled": False}
    options.update(kwargs)
    return MemoryStage(writer or _Writer(), planner or _Planner(), **options)


async def test_memory_stage_disabled_or_empty() -> None:
    stage = _stage(enabled=False)
    assert await stage.run(recent_messages=[_msg(1)]) == 0
    stage = _stage()
    assert await stage.run(recent_messages=[]) == 0


async def test_memory_stage_extracts_and_watermarks() -> None:
    writer = _Writer()
    stage = _stage(writer=writer)
    written = await stage.run(recent_messages=[_msg(3)], telegram_chat_id=7)
    assert written == _WRITTEN
    assert writer.calls == 1
    again = await stage.run(recent_messages=[_msg(3)], telegram_chat_id=7)
    assert again == 0


async def test_memory_stage_cooldown_and_prefilter() -> None:
    stage = _stage(cooldown_seconds=60)
    first = await stage.run(recent_messages=[_msg(1)], telegram_chat_id=1)
    assert first == _WRITTEN
    blocked = await stage.run(recent_messages=[_msg(2)], telegram_chat_id=1)
    assert blocked == 0
    MemoryStage._last_run_by_chat.clear()
    MemoryStage._last_message_id_by_chat.clear()
    filtered = MemoryStage(
        _Writer(),
        _Planner(),
        cooldown_seconds=0,
        prefilter_enabled=True,
        prefilter_min_messages=1,
        prefilter_score_threshold=99.0,
    )
    assert await filtered.run(recent_messages=[_msg(1, "hi")]) == 0


async def test_memory_stage_plan_and_apply_errors() -> None:
    assert await _stage(planner=_Planner(error=True)).run(recent_messages=[_msg(1)]) == 0
    assert await _stage(writer=_Writer(error=True)).run(recent_messages=[_msg(1)]) == 0


async def test_memory_stage_none_ids_and_global_chat() -> None:
    messages = [
        ContextMessage(id=None, role="user", content="durable fact " * 8)  # type: ignore[arg-type]
    ]
    stage = _stage()
    written = await stage.run(recent_messages=messages, telegram_chat_id=None)
    assert written == _WRITTEN


async def test_memory_planner_parses_payload() -> None:
    class LLM:
        async def complete(self, *_a, **_k) -> str:
            return '{"updates": [{"type": "quote", "person": "Ada"}, "x"], "weekly_hint": "w"}'

    planner = MemoryPlanner(llm_client=LLM())
    plan = await planner.decide("Ada: hello")
    assert plan.weekly_hint == "w"
    assert plan.updates[0]["type"] == "quote"


async def test_memory_planner_bad_json() -> None:
    class LLM:
        async def complete(self, *_a, **_k) -> str:
            return "not-json"

    plan = await MemoryPlanner(llm_client=LLM()).decide("x")
    assert plan.updates == ()

    class ListLLM:
        async def complete(self, *_a, **_k) -> str:
            return "[]"

    assert (await MemoryPlanner(llm_client=ListLLM()).decide("x")).updates == ()

    class NoUpdates:
        async def complete(self, *_a, **_k) -> str:
            return '{"updates": "nope"}'

    assert (await MemoryPlanner(llm_client=NoUpdates()).decide("x")).updates == ()
