from __future__ import annotations

from services.agent.container.background import BackgroundJobs
from services.agent.container.broker import BrokerResources
from services.agent.container.decision import DecisionStack
from services.agent.container.knowledge import KnowledgeGraph
from services.agent.container.memes import MemeStack
from services.agent.container.metrics import Metrics
from services.agent.container.retrieval import RetrievalStack
from services.agent.container.role import ProcessRole


class ProcessGraph:
    def __init__(
        self,
        decision: DecisionStack | None = None,
        retrieval: RetrievalStack | None = None,
        memes: MemeStack | None = None,
        jobs: BackgroundJobs | None = None,
        knowledge: KnowledgeGraph | None = None,
        broker: BrokerResources | None = None,
        metrics: Metrics | None = None,
        role: ProcessRole | None = None,
    ) -> None:
        self.role = role or ProcessRole.from_settings()
        self.decision = decision or DecisionStack()
        self.retrieval = retrieval or RetrievalStack()
        self.memes = memes or MemeStack()
        self.jobs = jobs or BackgroundJobs()
        self.knowledge = knowledge or KnowledgeGraph(self.retrieval)
        self.broker = broker or BrokerResources(
            dispatch_tasks=self.role.dispatches_tasks,
        )
        self.metrics = metrics or Metrics()
