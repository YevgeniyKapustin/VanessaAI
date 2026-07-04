from unittest.mock import MagicMock, patch

import pytest

from app.rag.embeddings.local_embeddings import LocalEmbeddingProvider


@pytest.mark.asyncio
async def test_local_embedding_provider_returns_vector():
    provider = LocalEmbeddingProvider(cache_size=8, max_input_chars=100)
    fake_vector = [0.1, 0.2, 0.3]
    mock_model = MagicMock()
    mock_model.encode.return_value = fake_vector

    with patch("app.rag.embeddings.local_embeddings._load_model", return_value=mock_model):
        vector = await provider.embed("привет")

    assert vector == fake_vector
    mock_model.encode.assert_called_once()

@pytest.mark.asyncio
async def test_local_embedding_provider_uses_cache():
    provider = LocalEmbeddingProvider(cache_size=8, max_input_chars=100)
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.5, 0.6]

    with patch("app.rag.embeddings.local_embeddings._load_model", return_value=mock_model):
        first = await provider.embed("кэш")
        second = await provider.embed("кэш")

    assert first == second
    assert mock_model.encode.call_count == 1


@pytest.mark.asyncio
async def test_local_embedding_provider_embed_batch():
    provider = LocalEmbeddingProvider(cache_size=8, max_input_chars=100)
    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1], [0.2]]

    with patch("app.rag.embeddings.local_embeddings._load_model", return_value=mock_model):
        vectors = await provider.embed_batch(["a", "b"])

    assert vectors == [[0.1], [0.2]]


@pytest.mark.asyncio
async def test_local_embedding_provider_embed_batch_empty():
    provider = LocalEmbeddingProvider()
    assert await provider.embed_batch([]) == []


@pytest.mark.asyncio
async def test_local_embedding_provider_evicts_old_cache_entries():
    provider = LocalEmbeddingProvider(cache_size=1, max_input_chars=100)
    mock_model = MagicMock()
    mock_model.encode.side_effect = [[0.1], [0.2]]

    with patch("app.rag.embeddings.local_embeddings._load_model", return_value=mock_model):
        await provider.embed("first")
        await provider.embed("second")

    assert mock_model.encode.call_count == 2


def test_preload_embedding_model():
    mock_model = MagicMock()
    with patch(
        "app.rag.embeddings.local_embeddings._load_model",
        return_value=mock_model,
    ) as load:
        from app.rag.embeddings.local_embeddings import preload_embedding_model

        preload_embedding_model()
        load.assert_called_once()
