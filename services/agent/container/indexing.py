from services.agent.container.graph import ProcessGraph
from vanessa.config.settings import settings
from vanessa.core.protocols import MessageIndexingSchedulerProtocol
from vanessa.infrastructure.db.repository import MessageRepository
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.pipeline.indexing.message_indexing import MessageIndexingService
from vanessa.pipeline.rag.search.hybrid_search import HybridSearchService


class Indexing:
    def __init__(self, graph: ProcessGraph) -> None:
        self._graph = graph

    def task_dispatcher(self):
        return self._graph.broker.task_dispatcher()

    def messages(
        self,
        messages: MessageRepository,
        hybrid_search: HybridSearchService,
    ) -> MessageIndexingSchedulerProtocol:
        return MessageIndexingService(
            indexer=hybrid_search,
            messages=messages,
            session_factory=async_session_factory,
            max_retries=settings.indexing_max_retries,
            background=self._graph.jobs.executor,
            dispatcher=self.task_dispatcher(),
        )
