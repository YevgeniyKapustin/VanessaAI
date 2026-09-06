import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from vanessa.config import settings
from vanessa.core.protocols import VectorSearchHit
from vanessa.pipeline.rag.knowledge_qdrant import KnowledgeQdrantStore
from vanessa.pipeline.rag.qdrant_collection import (
    ensure_qdrant_collection,
    upsert_qdrant_points,
)

__all__ = ["KnowledgeQdrantStore", "QdrantVectorStore"]


class QdrantVectorStore:
    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        collection: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        self._client = client or AsyncQdrantClient(url=settings.qdrant_url)
        self._collection = collection or settings.qdrant_collection
        self._vector_size = vector_size or settings.embedding_dimensions

    async def ensure_collection(self) -> None:
        await ensure_qdrant_collection(
            self._client, self._collection, self._vector_size
        )

    async def upsert_message(
        self,
        message_id: int,
        role: str,
        content: str,
        vector: list[float],
        point_id: str | None = None,
    ) -> str:
        del role, content
        pid = point_id or str(uuid.uuid4())
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload={"message_id": message_id},
                )
            ],
        )
        return pid

    async def upsert_batch(
        self,
        items: list[tuple[int, list[float], str | None]],
    ) -> list[str]:
        points: list[PointStruct] = []
        point_ids: list[str] = []
        for message_id, vector, point_id in items:
            pid = point_id or str(uuid.uuid4())
            point_ids.append(pid)
            points.append(
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload={"message_id": message_id},
                )
            )
        return await upsert_qdrant_points(
            self._client, self._collection, points, point_ids
        )

    async def search(
        self,
        vector: list[float],
        limit: int = 30,
    ) -> list[VectorSearchHit]:
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        return [
            VectorSearchHit(
                message_id=hit.payload["message_id"],
                score=hit.score,
            )
            for hit in response.points
            if hit.payload
        ]
