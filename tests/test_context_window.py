from datetime import datetime, timezone

import pytest

from app.core.messages import ContextBlock, ContextMessage, StoredMessage
from app.llm.prompt_builder import PromptBuilder


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
                created_at=datetime(2023, 5, 1, 14, 30, tzinfo=timezone.utc),
            ),
            ContextMessage(
                id=42,
                role="user",
                content="про крабера",
                sender_name="bob",
                created_at=datetime(2023, 5, 1, 14, 31, tzinfo=timezone.utc),
                is_anchor=True,
            ),
        ),
    )

    text = builder.format_context_block(1, block)

    assert "--- Фрагмент 1 (" in text
    assert "01.05.2023" in text
    assert "[user:alice]" in text
    assert "← совпадение с запросом" in text
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
                    created_at=datetime(2022, 1, 1, 10, 0, tzinfo=timezone.utc),
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
                    created_at=datetime(2026, 7, 3, 18, 0, tzinfo=timezone.utc),
                ),
            ),
        ),
    ]

    prompt = builder.build_user_prompt("вопрос", blocks)

    assert prompt.count("--- Фрагмент") == 2
    assert "Фрагмент 1" in prompt
    assert "Фрагмент 2" in prompt
    assert "первый" in prompt
    assert "второй" in prompt
    assert "первый\n\n--- Фрагмент 2" in prompt


@pytest.mark.asyncio
async def test_hybrid_search_returns_blocks(monkeypatch):
    from app.rag.hybrid_search import HybridSearchService

    class FakeRepo:
        async def fulltext_search(self, query: str, limit: int = 30) -> list[StoredMessage]:
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

    class FakeEmbeddings:
        async def embed(self, text: str) -> list[float]:
            return [0.1, 0.2]

    class FakeVectorStore:
        async def search(self, vector: list[float], limit: int = 30):
            return [{"message_id": 42, "score": 0.95}]

    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "app.rag.hybrid_search.get_content",
        lambda: type("C", (), {"rag": type("R", (), {"vector_min_score": 0.35})()})(),
    )

    service = HybridSearchService(FakeRepo(), FakeEmbeddings(), FakeVectorStore())
    result = await service.search("крабер")

    assert len(result) == 1
    assert result[0].anchor_id == 42
    assert len(result[0].messages) == 2
    assert result[0].messages[1].is_anchor is True
    assert result[0].messages[1].content == "якорь"
    assert all(message.role == "user" for message in result[0].messages)


@pytest.mark.asyncio
async def test_hybrid_search_skips_assistant_anchors(monkeypatch):
    from app.rag.hybrid_search import HybridSearchService

    class FakeRepo:
        async def fulltext_search(self, query: str, limit: int = 30):
            return []

        async def get_by_ids(self, message_ids: list[int]) -> list[StoredMessage]:
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
            return [
                (
                    42,
                    [
                        StoredMessage(id=42, role="user", content="про крабера"),
                    ],
                )
            ]

    class FakeEmbeddings:
        async def embed(self, text: str) -> list[float]:
            return [0.1, 0.2]

    class FakeVectorStore:
        async def search(self, vector: list[float], limit: int = 30):
            return [{"message_id": 99, "score": 0.99}, {"message_id": 42, "score": 0.5}]

    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_anchor_max", 5)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "app.rag.hybrid_search.get_content",
        lambda: type("C", (), {"rag": type("R", (), {"vector_min_score": 0.35})()})(),
    )

    service = HybridSearchService(FakeRepo(), FakeEmbeddings(), FakeVectorStore())
    result = await service.search("крабер")

    assert len(result) == 1
    assert result[0].anchor_id == 42
    assert result[0].messages[0].content == "про крабера"


@pytest.mark.asyncio
async def test_hybrid_search_passes_budget_for_ten_anchors(monkeypatch):
    from app.rag.hybrid_search import HybridSearchService, effective_window_max_total

    seen: dict[str, int] = {}

    class FakeRepo:
        async def fulltext_search(self, query: str, limit: int = 30):
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
            seen["anchor_count"] = len(anchor_ids)
            seen["max_total"] = max_total
            return [
                (anchor_id, [StoredMessage(id=anchor_id, role="user", content="x")])
                for anchor_id in anchor_ids
            ]

    class FakeEmbeddings:
        async def embed(self, text: str) -> list[float]:
            return [0.1, 0.2]

    class FakeVectorStore:
        async def search(self, vector: list[float], limit: int = 30):
            return [
                {"message_id": index, "score": 0.9 - index * 0.01}
                for index in range(1, 11)
            ]

    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_anchor_max", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_before", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_after", 10)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_context_window_max_total", 80)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_vector_min_score", 0.35)
    monkeypatch.setattr("app.rag.hybrid_search.settings.rag_hybrid_top_k", 20)
    monkeypatch.setattr(
        "app.rag.hybrid_search.get_content",
        lambda: type("C", (), {"rag": type("R", (), {"vector_min_score": 0.35})()})(),
    )

    service = HybridSearchService(FakeRepo(), FakeEmbeddings(), FakeVectorStore())
    result = await service.search("крабер")

    assert seen["anchor_count"] == 10
    assert seen["max_total"] == effective_window_max_total(10)
    assert len(result) == 10
