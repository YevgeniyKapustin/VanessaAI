from services.agent.container.graph import ProcessGraph
from vanessa.core.protocols import (
    EmbeddingProviderProtocol,
    MessageRepositoryProtocol,
    VectorStoreProtocol,
)
from vanessa.knowledge.participants import ParticipantsDigest
from vanessa.pipeline.rag.query_rewriter import QueryRewriter
from vanessa.pipeline.rag.search.hybrid_search import HybridSearchService


class Search:
    def __init__(
        self,
        graph: ProcessGraph,
        participants: ParticipantsDigest | None = None,
    ) -> None:
        self._graph = graph
        self._participants = participants

    def hybrid(
        self,
        messages: MessageRepositoryProtocol,
        embeddings: EmbeddingProviderProtocol,
        vector_store: VectorStoreProtocol,
    ) -> HybridSearchService:
        return HybridSearchService(
            message_repo=messages,
            embedding_provider=embeddings,
            vector_store=vector_store,
        )

    def participants_digest(self) -> ParticipantsDigest:
        if self._participants is None:
            knowledge = self._graph.knowledge
            self._participants = ParticipantsDigest(
                knowledge.vault,
                knowledge.index,
            )
        return self._participants

    def query_rewriter(self) -> QueryRewriter:
        return QueryRewriter(
            participants_provider=self.participants_digest().build,
        )
