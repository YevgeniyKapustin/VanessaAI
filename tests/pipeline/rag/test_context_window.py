from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from vanessa.core.messages import ContextBlock, ContextMessage, StoredMessage
from vanessa.pipeline.llm.prompts.prompt_builder import PromptBuilder
from vanessa.pipeline.rag.search.hybrid_search import (
    HybridSearchService,
    effective_window_max_total,
)

ANCHOR_ID = 42


def _stub_get_content(vector_min_score: float = 0.35):
    rag = type("R", (), {"vector_min_score": vector_min_score})()
    content = type("C", (), {"rag": rag})()

    def get_content():
        return content

    return get_content


class _FixedEmbeddings:
    async def embed(self, text: str) -> list[float]:
        _ = text
        return [0.1, 0.2]


class _BlocksRepo:
    async def fulltext_search(self, query: str, limit: int = 30) -> list[StoredMessage]:
        _ = query, limit
        return []

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]:
        messages = {
            40: StoredMessage(
                id=40,
                role="user",
                content="до",
                sender_name="alice",
            ),
            42: StoredMessage(
                id=42,
                role="user",
                content="якорь",
                sender_name="bob",
            ),
        }
        return [messages[mid] for mid in message_ids if mid in messages]

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ) -> list[tuple[int, list[StoredMessage]]]:
        _ = before, after, max_total
        assert anchor_ids == [42]
        return [
            (
                42,
                [
                    StoredMessage(
                        id=40,
                        role="user",
                        content="до",
                        sender_name="alice",
                    ),
                    StoredMessage(
                        id=42,
                        role="user",
                        content="якорь",
                        sender_name="bob",
                    ),
                ],
            )
        ]


class _BlocksVectorStore:
    async def search(self, vector: list[float], limit: int = 30):
        _ = vector, limit
        return [{"message_id": 42, "score": 0.95}]


class _SkipAssistantRepo:
    async def fulltext_search(self, query: str, limit: int = 30):
        _ = query, limit
        return []

    async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]:
        _ = message_ids
        return [
            StoredMessage(id=99, role="assistant", content="ответ бота"),
            StoredMessage(id=42, role="user", content="про крабера"),
        ]

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ):
        _ = anchor_ids, before, after, max_total
        return [
            (
                42,
                [
                    StoredMessage(id=42, role="user", content="про крабера"),
                ],
            )
        ]


class _SkipAssistantVectorStore:
    async def search(self, vector: list[float], limit: int = 30):
        _ = vector, limit
        return [{"message_id": 99, "score": 0.99}, {"message_id": 42, "score": 0.5}]


class _BudgetRepo:
    def __init__(self, seen: dict[str, int]) -> None:
        self._seen = seen

    async def fulltext_search(self, query: str, limit: int = 30):
        _ = query, limit
        return []

    async def get_by_ids(self, message_ids: list[int]):
        return [
            StoredMessage(id=mid, role="user", content=f"msg-{mid}")
            for mid in message_ids
        ]

    async def get_conversation_window_blocks(
        self,
        anchor_ids: list[int],
        before: int = 10,
        after: int = 10,
        max_total: int = 80,
    ):
        _ = before, after
        self._seen["anchor_count"] = len(anchor_ids)
        self._seen["max_total"] = max_total
        return [
            (anchor_id, [StoredMessage(id=anchor_id, role="user", content="x")])
            for anchor_id in anchor_ids
        ]


class _BudgetVectorStore:
    async def search(self, vector: list[float], limit: int = 30):
        _ = vector, limit
        return [
            {"message_id": index, "score": 0.9 - index * 0.01}
            for index in range(1, 11)
        ]


def test_prompt_builder_formats_block_with_time_and_anchor():
    builder = PromptBuilder()
    block = ContextBlock(
        anchor_id=42,
        messages=(
            ContextMessage(
                id=40,
                role="user",
                content="до",
                sender_name="alice",
                created_at=datetime(2023, 5, 1, 14, 30, tzinfo=UTC),
            ),
            ContextMessage(
                id=42,
                role="user",
                content="про крабера",
                sender_name="bob",
                created_at=datetime(2023, 5, 1, 14, 31, tzinfo=UTC),
                is_anchor=True,
            ),
        ),
    )

    text = builder.format_context_block(1, block)

    assert "<!-- Block 1 (" in text
    assert "01.05.2023" in text
    assert 'sender="alice"' in text
    assert 'anchor="true"' in text
    assert "про крабера" in text


def test_prompt_builder_builds_separated_blocks():
    builder = PromptBuilder()
    blocks = [
        ContextBlock(
            anchor_id=1,
            messages=(
                ContextMessage(
                    id=1,
                    role="user",
                    content="первый",
                    created_at=datetime(2022, 1, 1, 10, 0, tzinfo=UTC),
                ),
            ),
        ),
        ContextBlock(
            anchor_id=2,
            messages=(
                ContextMessage(
                    id=2,
                    role="user",
                    content="второй",
                    created_at=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
                ),
            ),
        ),
    ]

    prompt = builder.build_user_prompt("вопрос", blocks)

    expected_blocks = 2
    assert prompt.count("<!-- Block") == expected_blocks
    assert "Block 1" in prompt
    assert "Block 2" in prompt
    assert "первый" in prompt
    assert "второй" in prompt
    assert "</messages>\n\n<!-- Block 2" in prompt


@pytest.mark.asyncio
async def test_hybrid_search_returns_blocks(monkeypatch):
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.get_content",
        _stub_get_content(0.35),
    )

    service = HybridSearchService(_BlocksRepo(), _FixedEmbeddings(), _BlocksVectorStore())
    result = await service.search("крабер")

    assert len(result) == 1
    assert result[0].anchor_id == ANCHOR_ID
    expected_messages = 2
    assert len(result[0].messages) == expected_messages
    assert result[0].messages[1].is_anchor is True
    assert result[0].messages[1].content == "якорь"
    assert all(message.role == "user" for message in result[0].messages)


@pytest.mark.asyncio
async def test_hybrid_search_skips_assistant_anchors(monkeypatch):
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.get_content",
        _stub_get_content(0.35),
    )

    service = HybridSearchService(
        _SkipAssistantRepo(),
        _FixedEmbeddings(),
        _SkipAssistantVectorStore(),
    )
    result = await service.search("крабер")

    assert len(result) == 1
    assert result[0].anchor_id == ANCHOR_ID
    assert result[0].messages[0].content == "про крабера"


@pytest.mark.asyncio
async def test_hybrid_search_passes_budget_for_ten_anchors(monkeypatch):
    seen: dict[str, int] = {}

    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_anchor_max", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.get_content",
        _stub_get_content(0.35),
    )

    service = HybridSearchService(
        _BudgetRepo(seen),
        _FixedEmbeddings(),
        _BudgetVectorStore(),
    )
    result = await service.search("крабер")

    expected_anchors = 10
    assert seen["anchor_count"] == expected_anchors
    assert seen["max_total"] == effective_window_max_total(expected_anchors)
    assert len(result) == expected_anchors


@pytest.mark.asyncio
async def test_hybrid_search_empty_query_returns_nothing():

    service = HybridSearchService(AsyncMock(), AsyncMock(), AsyncMock())
    assert await service.search("   ") == []


@pytest.mark.asyncio
async def test_hybrid_search_embed_query():

    embeddings = AsyncMock()
    embeddings.embed = AsyncMock(return_value=[0.1, 0.2])
    service = HybridSearchService(AsyncMock(), embeddings, AsyncMock())

    assert await service.embed_query("q") == [0.1, 0.2]


@pytest.mark.asyncio
async def test_hybrid_search_index_skips_non_user_role():

    embeddings = AsyncMock()
    vector_store = AsyncMock()
    service = HybridSearchService(AsyncMock(), embeddings, vector_store)

    assert await service.index(1, "assistant", "bot", point_id="keep") == "keep"
    embeddings.embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_hybrid_search_uses_semantic_queries(monkeypatch):


    class FakeRepo:
        async def fulltext_search(self, query: str, limit: int = 30):
            _ = query, limit
            return []

        async def get_by_ids(self, message_ids: list[int]):
            return [
                StoredMessage(id=mid, role="user", content=f"m-{mid}")
                for mid in message_ids
            ]

        async def get_conversation_window_blocks(self, **kwargs):
            anchor_ids = kwargs["anchor_ids"]
            return [
                (anchor_id, [StoredMessage(id=anchor_id, role="user", content="x")])
                for anchor_id in anchor_ids
            ]

    embeddings = AsyncMock()
    embeddings.embed_batch = AsyncMock(return_value=[[0.1], [0.2]])
    vector_store = AsyncMock()
    vector_store.search = AsyncMock(
        return_value=[{"message_id": 5, "score": 0.9}]
    )

    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_before",
        1,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_after",
        1,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_max_total",
        80,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_vector_min_score",
        0.1,
    )
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.get_content",
        _stub_get_content(0.1),
    )

    service = HybridSearchService(FakeRepo(), embeddings, vector_store)
    result = await service.search(
        "",
        semantic_queries=["Alpha", "alpha", "  ", "Beta"],
        skip_fts=True,
    )

    embeddings.embed_batch.assert_awaited_once_with(["Alpha", "Beta"])
    assert len(result) == 1


@pytest.mark.asyncio
async def test_hybrid_search_without_window_expansion(monkeypatch):

    class FakeRepo:
        async def fulltext_search(self, query: str, limit: int = 30):
            _ = query, limit
            return []

        async def get_by_ids(self, message_ids: list[int]):
            return [
                StoredMessage(id=mid, role="user", content=f"m-{mid}")
                for mid in message_ids
            ]

    embeddings = AsyncMock()
    embeddings.embed = AsyncMock(return_value=[0.1])
    vector_store = AsyncMock()
    vector_store.search = AsyncMock(
        return_value=[{"message_id": 7, "score": 0.95}]
    )

    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_before",
        0,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_context_window_after",
        0,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.settings.rag_vector_min_score",
        0.1,
    )
    monkeypatch.setattr("vanessa.pipeline.rag.search.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "vanessa.pipeline.rag.search.hybrid_search.get_content",
        _stub_get_content(0.1),
    )

    service = HybridSearchService(FakeRepo(), embeddings, vector_store)
    result = await service.search("крабер")

    low_score_anchor = 7
    assert len(result) == 1
    assert result[0].anchor_id == low_score_anchor
