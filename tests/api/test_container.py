from unittest.mock import MagicMock

from services.agent.container import (
    AppContainer,
    BackgroundJobs,
    DecisionStack,
    KnowledgeGraph,
    MemeStack,
    ProcessGraph,
    ProcessRole,
    TurnWiring,
)
from services.agent.container.broker import BrokerResources
from services.agent.container.turns.orchestrator import OrchestratorFactory
from vanessa.config.settings import settings
from vanessa.infrastructure.hermes import HermesClient


def test_process_graph_composes_stacks() -> None:
    decision = MagicMock()
    memes = MagicMock()
    jobs = MagicMock()
    knowledge = MagicMock()
    broker = MagicMock()
    graph = ProcessGraph(
        decision=decision,
        memes=memes,
        jobs=jobs,
        knowledge=knowledge,
        broker=broker,
    )
    assert graph.decision is decision
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
    wiring = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
    )
    assert wiring.graph is graph
    assert wiring.persistence is persistence
    assert wiring.search is search
    assert wiring.role is ProcessRole.from_settings()


def test_turn_wiring_handler_builds_from_session() -> None:
    graph = MagicMock()
    persistence = MagicMock()
    search = MagicMock()
    orchestrator = MagicMock()
    wiring = TurnWiring(
        graph,
        persistence=persistence,
        search=search,
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


def test_knowledge_graph_holds_vault_and_index() -> None:
    vault = MagicMock()
    index = MagicMock()
    graph = KnowledgeGraph(vault=vault, index=index)
    assert graph.vault is vault
    assert graph.index is index
    assert graph.vault_writer() is not None


def test_jobs_and_memes_are_objects() -> None:
    jobs = BackgroundJobs(executor=MagicMock())
    memes = MemeStack(catalog=MagicMock(), decider=MagicMock())
    assert jobs.executor is not None
    assert memes.catalog is not None


def test_broker_resources_reuse_client() -> None:
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
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
        role=ProcessRole.DISPATCH,
    )
    engines = wiring.engines()
    assert engines.memory is None
    assert engines.metrics is None
    assert engines.photo is None


def _dispatch_wiring() -> TurnWiring:
    return TurnWiring(
        MagicMock(),
        search=MagicMock(),
        decision_factory=MagicMock(),
        orchestrator=MagicMock(),
        role=ProcessRole.DISPATCH,
    )


def test_engines_build_hermes_client_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_url", "http://hermes:8642")
    assert isinstance(_dispatch_wiring().engines().hermes, HermesClient)


def test_engines_skip_hermes_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_enabled", False)
    assert _dispatch_wiring().engines().hermes is None


def test_orchestrator_wires_hermes_into_retrieve() -> None:
    graph = MagicMock()
    engines = MagicMock()
    orchestrator = OrchestratorFactory(graph).build(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(), engines
    )
    retrieve = orchestrator._retrieve
    dispatcher = graph.broker.task_dispatcher.return_value
    assert retrieve._hermes is engines.hermes
    assert retrieve._dispatcher is dispatcher
    assert orchestrator._dispatcher is dispatcher
