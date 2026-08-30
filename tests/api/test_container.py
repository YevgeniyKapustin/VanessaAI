from unittest.mock import MagicMock

from services.agent.container import (
    AppContainer,
    BackgroundJobs,
    DecisionStack,
    KnowledgeGraph,
    MemeStack,
    ProcessGraph,
    ProcessRole,
    RetrievalStack,
    TurnWiring,
)


def test_process_graph_composes_stacks() -> None:
    decision = MagicMock()
    retrieval = MagicMock()
    memes = MagicMock()
    jobs = MagicMock()
    knowledge = MagicMock()
    broker = MagicMock()
    graph = ProcessGraph(
        decision=decision,
        retrieval=retrieval,
        memes=memes,
        jobs=jobs,
        knowledge=knowledge,
        broker=broker,
    )
    assert graph.decision is decision
    assert graph.retrieval is retrieval
    assert graph.memes is memes
    assert graph.jobs is jobs
    assert graph.knowledge is knowledge
    assert graph.broker is broker
    assert graph.role is ProcessRole.from_settings()


def test_app_container_holds_graph_and_turns() -> None:
    graph = MagicMock()
    turns = MagicMock()
    app = AppContainer(graph=graph, turns=turns)
    assert app.graph is graph
    assert app.turns is turns


def test_turn_wiring_uses_graph() -> None:
    graph = MagicMock()
    persistence = MagicMock()
    search = MagicMock()
    indexing = MagicMock()
    wiring = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
        indexing=indexing,
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
    )
    assert wiring.graph is graph
    assert wiring.persistence is persistence
    assert wiring.search is search
    assert wiring.indexing is indexing
    assert wiring.role is ProcessRole.from_settings()


def test_turn_wiring_handler_builds_from_session() -> None:
    graph = MagicMock()
    persistence = MagicMock()
    search = MagicMock()
    indexing = MagicMock()
    orchestrator = MagicMock()
    wiring = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
        indexing=indexing,
        decision_factory=MagicMock(),
        orchestrator=orchestrator,
    )
    session = MagicMock()
    wiring.handler(session)
    orchestrator.build.assert_called_once()
    engines = orchestrator.build.call_args.args[-1]
    wiring.handler(session)
    assert orchestrator.build.call_args.args[-1] is engines


def test_decision_stack_accepts_collaborators() -> None:
    signals = MagicMock()
    eligibility = MagicMock()
    stack = DecisionStack(
        signals=signals,
        ignore_registry=MagicMock(),
        rate_limiter=MagicMock(),
        eligibility=eligibility,
        reaction_gate=MagicMock(),
    )
    assert stack.signals is signals
    assert stack.eligibility is eligibility


def test_knowledge_graph_uses_retrieval() -> None:
    retrieval = MagicMock()
    vault = MagicMock()
    index = MagicMock()
    indexer = MagicMock()
    graph = KnowledgeGraph(
        retrieval,
        vault=vault,
        index=index,
        vector_indexer=indexer,
    )
    assert graph.vault is vault
    assert graph.index is index
    assert graph.vector_indexer is indexer


def test_retrieval_and_jobs_are_objects() -> None:
    indexes = MagicMock()
    retrieval = RetrievalStack(embeddings=MagicMock(), indexes=indexes)
    jobs = BackgroundJobs(executor=MagicMock())
    memes = MemeStack(catalog=MagicMock(), decider=MagicMock())
    assert retrieval.indexes is indexes
    assert jobs.executor is not None
    assert memes.catalog is not None


def test_broker_resources_reuse_client() -> None:
    from services.agent.container.broker import BrokerResources

    first = object()
    broker = BrokerResources(client=first, dispatch_tasks=False)
    assert broker.ensure_client() is first
    assert broker.ensure_client() is first
    assert broker.task_dispatcher() is None


def test_process_role_from_settings() -> None:
    assert ProcessRole.from_settings(worker_enabled=False) is ProcessRole.INLINE
    assert ProcessRole.from_settings(worker_enabled=True) is ProcessRole.DISPATCH
    assert ProcessRole.INLINE.owns_knowledge_loops
    assert ProcessRole.DISPATCH.dispatches_tasks
    assert not ProcessRole.DISPATCH.inline_turn_effects


def test_app_container_accepts_role() -> None:
    app = AppContainer(role=ProcessRole.DISPATCH)
    assert app.role is ProcessRole.DISPATCH
    assert app.graph.role is ProcessRole.DISPATCH
    assert app.turns.role is ProcessRole.DISPATCH


def test_worker_role_skips_inline_engines() -> None:
    wiring = TurnWiring(
        MagicMock(),
        search=MagicMock(),
        indexing=MagicMock(),
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
        role=ProcessRole.DISPATCH,
    )
    engines = wiring.engines()
    assert engines.memory is None
    assert engines.metrics is None
    assert engines.photo is None
