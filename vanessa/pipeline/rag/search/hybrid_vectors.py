from vanessa.core.protocols import EmbeddingProviderProtocol


def _unique_embed_texts(semantic_queries: list[str] | None) -> list[str]:
    embed_texts: list[str] = []
    seen: set[str] = set()
    for text in semantic_queries or []:
        normalized = text.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        embed_texts.append(normalized)
    return embed_texts


async def resolve_search_vectors(
    embeddings: EmbeddingProviderProtocol,
    query: str,
    query_vector: list[float] | None,
    semantic_queries: list[str] | None,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    if query_vector is not None:
        vectors.append(query_vector)
    embed_texts = _unique_embed_texts(semantic_queries)
    if embed_texts:
        vectors.extend(await embeddings.embed_batch(embed_texts))
    if not vectors:
        vectors.append(await embeddings.embed(query))
    return vectors
