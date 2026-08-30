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

from vanessa.config import settings
from vanessa.core.protocols import KnowledgeVectorHit, VectorSearchHit


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


class KnowledgeQdrantStore:
    """Vector store for the semantic knowledge vault notes.

    A separate Qdrant collection holds one point per vault note, keyed by the
    note's vault-relative path (deterministic point id). Re-embedding a note
    after a memory write overwrites its point in place, so the index never
    accumulates stale vectors for renamed/merged cards.
    """

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        collection: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        self._client = client or AsyncQdrantClient(url=settings.qdrant_url)
        self._collection = collection or settings.qdrant_knowledge_collection
        self._vector_size = vector_size or settings.embedding_dimensions

    @staticmethod
    def point_id(path: str) -> str:
        """Deterministic UUID point id derived from the note's vault-relative path.

        Qdrant only accepts unsigned-integer or UUID point ids; a bare ``k:...``
        hash string is rejected with HTTP 400 by modern Qdrant versions (this
        silently kept the ``knowledge`` collection empty). Deriving a UUID keeps
        the id deterministic so re-embedding a note overwrites its point in
        place (idempotent reindex).
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vault://{path}"))

    @staticmethod
    def chunk_point_id(path: str, chunk_index: int) -> str:
        """Deterministic UUID point id for a People-dossier chunk (per-chunk points).

        Each (path, chunk_index) pair maps to its own UUID so every block of a
        People dossier is stored and re-indexed independently.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vault://{path}#{chunk_index}"))

    async def reset(self) -> None:
        """Drop the whole collection (used by a full reindex)."""
        await self._client.delete_collection(self._collection)

    async def ensure_collection(self) -> None:
        collections = await self._client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self._collection in names:
            return
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=self._vector_size,
                distance=Distance.COSINE,
                on_disk=settings.qdrant_on_disk,
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=settings.qdrant_indexing_threshold,
            ),
            hnsw_config=HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
                on_disk=settings.qdrant_on_disk,
            ),
            **(
                {
                    "quantization_config": ScalarQuantization(
                        scalar=ScalarQuantizationConfig(
                            type=ScalarType.INT8,
                            always_ram=False,
                        ),
                    )
                }
                if settings.qdrant_quantization_enabled
                else {}
            ),
        )

    async def upsert_note(
        self,
        path: str,
        kind: str,
        title: str,
        vector: list[float],
    ) -> str:
        pid = self.point_id(path)
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload={"path": path, "kind": kind, "title": title},
                )
            ],
        )
        return pid

    async def upsert_notes(
        self,
        items: list[tuple[str, str, str, list[float]]],
    ) -> list[str]:
        points: list[PointStruct] = []
        point_ids: list[str] = []
        for path, kind, title, vector in items:
            pid = self.point_id(path)
            point_ids.append(pid)
            points.append(
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload={"path": path, "kind": kind, "title": title},
                )
            )
        if not points:
            return []
        await self._client.upsert(
            collection_name=self._collection,
            points=points,
        )
        return point_ids

    async def upsert_note_chunks(
        self,
        path: str,
        kind: str,
        title: str,
        chunks: list[tuple[int, str]],
        vectors: list[list[float]],
    ) -> list[str]:
        """Upsert one point per dossier chunk, keyed by (path, chunk_index).

        Each chunk keeps the note path in its payload plus a ``chunk_index`` so
        ``search`` can return the strongest individual blocks of a People
        dossier. Re-embedding a note overwrites its chunk points in place
        (deterministic ids), never accumulating stale vectors.
        """
        points: list[PointStruct] = []
        point_ids: list[str] = []
        for (chunk_index, _chunk_text), vector in zip(chunks, vectors):
            pid = self.chunk_point_id(path, chunk_index)
            point_ids.append(pid)
            points.append(
                PointStruct(
                    id=pid,
                    vector=vector,
                    payload={
                        "path": path,
                        "kind": kind,
                        "title": title,
                        "chunk_index": chunk_index,
                    },
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
    ) -> list[KnowledgeVectorHit]:
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        hits: list[KnowledgeVectorHit] = []
        for hit in response.points:
            payload = hit.payload or {}
            path = payload.get("path")
            if not path:
                continue
            chunk_index = payload.get("chunk_index")
            knowledge_hit: KnowledgeVectorHit = {
                "path": str(path),
                "kind": str(payload.get("kind") or ""),
                "title": str(payload.get("title") or ""),
                "score": hit.score,
            }
            if chunk_index is not None:
                knowledge_hit["chunk_index"] = int(chunk_index)
            hits.append(knowledge_hit)
        return hits
