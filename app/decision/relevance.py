from app.core.protocols import EmbeddingProviderProtocol, VectorStoreProtocol
from app.decision.protocols import RelevanceCheckerProtocol


class QdrantRelevanceChecker:
    def __init__(
        self,
        embedding_provider: EmbeddingProviderProtocol,
        vector_store: VectorStoreProtocol,
    ) -> None:
        self._embeddings = embedding_provider
        self._vector_store = vector_store

    async def score(
        self,
        text: str,
        query_vector: list[float] | None = None,
        search_text: str | None = None,
    ) -> float:
        effective = (search_text if search_text is not None else text).strip()
        if not effective:
            return 0.0
        vector = query_vector or await self._embeddings.embed(effective)
        hits = await self._vector_store.search(
            vector=vector,
            limit=1,
        )
        if not hits:
            return 0.0
        return float(hits[0]["score"])
