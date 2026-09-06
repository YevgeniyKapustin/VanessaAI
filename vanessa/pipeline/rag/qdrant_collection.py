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


def collection_create_kwargs(collection_name: str, vector_size: int) -> dict:
    kwargs: dict = {
        "collection_name": collection_name,
        "vectors_config": VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
            on_disk=settings.qdrant_on_disk,
        ),
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
    return kwargs


async def ensure_qdrant_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int,
) -> None:
    collections = await client.get_collections()
    names = {collection.name for collection in collections.collections}
    if collection_name in names:
        return
    await client.create_collection(
        **collection_create_kwargs(collection_name, vector_size)
    )


async def upsert_qdrant_points(
    client: AsyncQdrantClient,
    collection_name: str,
    points: list[PointStruct],
    point_ids: list[str],
) -> list[str]:
    if not points:
        return []
    await client.upsert(
        collection_name=collection_name,
        points=points,
    )
    return point_ids
