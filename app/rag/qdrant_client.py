import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

from app.config import settings
from app.core.protocols import VectorSearchHit


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
        collections = await self._client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self._collection in names:
            return

        vectors_config = VectorParams(
            size=self._vector_size,
            distance=Distance.COSINE,
            on_disk=settings.qdrant_on_disk,
        )
        kwargs: dict = {
            "collection_name": self._collection,
            "vectors_config": vectors_config,
            "optimizers_config": OptimizersConfigDiff(
                indexing_threshold=settings.qdrant_indexing_threshold,
            ),
            "hnsw_config": HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
                on_disk=settings.qdrant_on_disk,
            ),
        }
        if settings.qdrant_quantization_enabled:
            kwargs["quantization_config"] = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    always_ram=False,
                ),
            )

        await self._client.create_collection(**kwargs)

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
        if not points:
            return []
        await self._client.upsert(
            collection_name=self._collection,
            points=points,
        )
        return point_ids

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
