from unittest.mock import MagicMock, patch

import pytest

from app.rag.local_embeddings import LocalEmbeddingProvider


@pytest.mark.asyncio
async def test_local_embedding_provider_returns_vector():
    provider = LocalEmbeddingProvider(cache_size=8, max_input_chars=100)
    fake_vector = [0.1, 0.2, 0.3]
    mock_model = MagicMock()
    mock_model.encode.return_value = fake_vector

    with patch("app.rag.local_embeddings._load_model", return_value=mock_model):
        vector = await provider.embed("привет")

    assert vector == fake_vector
    mock_model.encode.assert_called_once()

@pytest.mark.asyncio
async def test_local_embedding_provider_uses_cache():
    provider = LocalEmbeddingProvider(cache_size=8, max_input_chars=100)
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.5, 0.6]

    with patch("app.rag.local_embeddings._load_model", return_value=mock_model):
        first = await provider.embed("кэш")
        second = await provider.embed("кэш")

    assert first == second
    assert mock_model.encode.call_count == 1
