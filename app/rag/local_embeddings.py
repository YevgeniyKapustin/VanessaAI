import asyncio
from collections import OrderedDict
from functools import lru_cache

from app.config import settings
from app.rag.text import truncate_for_embedding

_embed_lock = asyncio.Lock()


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name)


def preload_embedding_model() -> None:
    _load_model()


class LocalEmbeddingProvider:
    def __init__(
        self,
        cache_size: int | None = None,
        max_input_chars: int | None = None,
    ) -> None:
        self._cache_size = cache_size or settings.rag_embed_cache_size
        self._max_input_chars = max_input_chars or settings.rag_embed_max_chars
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    def _normalize(self, text: str) -> str:
        return truncate_for_embedding(text, self._max_input_chars)

    def _to_list(self, vector) -> list[float]:
        if hasattr(vector, "tolist"):
            return vector.tolist()
        return list(vector)

    def _encode_sync(self, text: str) -> list[float]:
        vector = _load_model().encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return self._to_list(vector)

    def _encode_batch_sync(self, texts: list[str]) -> list[list[float]]:
        vectors = _load_model().encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [self._to_list(vector) for vector in vectors]

    async def embed(self, text: str) -> list[float]:
        normalized = self._normalize(text)
        cached = self._cache.get(normalized)
        if cached is not None:
            self._cache.move_to_end(normalized)
            return cached

        async with _embed_lock:
            cached = self._cache.get(normalized)
            if cached is not None:
                self._cache.move_to_end(normalized)
                return cached
            vector = await asyncio.to_thread(self._encode_sync, normalized)
            self._cache[normalized] = vector
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
            return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        normalized = [self._normalize(text) for text in texts]
        async with _embed_lock:
            return await asyncio.to_thread(self._encode_batch_sync, normalized)
