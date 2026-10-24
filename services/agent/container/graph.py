from __future__ import annotations

from services.agent.container.background import BackgroundJobs
from services.agent.container.broker import BrokerResources
from services.agent.container.decision import DecisionStack
from services.agent.container.metrics import Metrics
from services.agent.container.retrieval import KnowledgeGraph, MemeStack
from services.agent.container.role import ProcessRole
from vanessa.config.settings import settings
from vanessa.core.hermes_answers import RecentAnswers


class ProcessGraph:
    def __init__(
        self,
        *,
        decision: DecisionStack | None = None,
        memes: MemeStack | None = None,
        jobs: BackgroundJobs | None = None,
        knowledge: KnowledgeGraph | None = None,
        broker: BrokerResources | None = None,
        metrics: Metrics | None = None,
        role: ProcessRole | None = None,
        hermes_answers: RecentAnswers | None = None,
    ) -> None:
        self.role = role or ProcessRole.from_settings()
        self.decision = decision or DecisionStack()
        self.memes = memes or MemeStack()
        self.jobs = jobs or BackgroundJobs()
        self.knowledge = knowledge or KnowledgeGraph()
        self.broker = broker or BrokerResources(
            dispatch_tasks=self.role.dispatches_tasks,
        )
        self.metrics = metrics or Metrics()
        # One per process: the turns read it, posted follow-ups fill it.
        self.hermes_answers = hermes_answers or RecentAnswers(
            window_seconds=settings.hermes_recent_answer_seconds
        )
