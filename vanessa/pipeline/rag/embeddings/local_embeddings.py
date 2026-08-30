import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from vanessa.config import settings
from vanessa.pipeline.rag.text import truncate_for_embedding

_embed_lock = asyncio.Lock()

_embed_executor: ThreadPoolExecutor | None = None


def _get_embed_executor() -> ThreadPoolExecutor:
    """Dedicated pool for CPU-bound SentenceTransformer inference.

    Kept separate from asyncio's default thread pool so embedding work never
    starves other ``asyncio.to_thread`` callers and its concurrency stays
    bounded (see ``EMBEDDING_THREADS``).
    """
    global _embed_executor
    if _embed_executor is None:
        _embed_executor = ThreadPoolExecutor(
            max_workers=max(1, settings.embedding_threads),
            thread_name_prefix="embed",
        )
    return _embed_executor


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

    async def _run_in_pool(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_get_embed_executor(), func, *args)

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
            vector = await self._run_in_pool(self._encode_sync, normalized)
            self._cache[normalized] = vector
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
            return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        normalized = [self._normalize(text) for text in texts]
        async with _embed_lock:
            return await self._run_in_pool(self._encode_batch_sync, normalized)
