import pytest

from app.core.messages import ContextBlock, ContextMessage
from app.llm.planner.turn_planner import TurnPlan
from app.rag.search.react_retriever import derive_follow_up_query, retrieve_with_react


class FakeRetriever:
    def __init__(self, results_per_call: list[list[ContextBlock]]) -> None:
        self._results = list(results_per_call)
        self.calls = 0

    async def search(self, **kwargs) -> list[ContextBlock]:
        self.calls += 1
        if not self._results:
            return []
        return self._results.pop(0)


def _block(anchor_id: int) -> ContextBlock:
    return ContextBlock(
        anchor_id=anchor_id,
        messages=(
            ContextMessage(id=anchor_id, role="user", content="тест контекст"),
        ),
    )


@pytest.mark.asyncio
async def test_retrieve_with_react_single_pass_when_not_deep():
    retriever = FakeRetriever([[_block(1)]])
    plan = TurnPlan(original="x", text="меш", skip_search=False, deep_search=False)

    blocks = await retrieve_with_react(retriever, "меш", plan)

    assert len(blocks) == 1
    assert retriever.calls == 1


@pytest.mark.asyncio
async def test_retrieve_with_react_multi_step_when_deep():
    retriever = FakeRetriever([[_block(1)], [_block(2)]])
    plan = TurnPlan(
        original="алгоритм генерации меша гексы",
        text="меш гексы",
        skip_search=False,
        deep_search=True,
    )

    blocks = await retrieve_with_react(retriever, plan.original, plan, max_steps=3)

    assert len(blocks) == 2
    assert retriever.calls >= 2


def test_derive_follow_up_returns_unused_token():
    blocks = [_block(1)]
    follow = derive_follow_up_query(
        "алгоритм генерации меша",
        blocks,
        ["меш гексы"],
    )
    assert follow == "алгоритм"
