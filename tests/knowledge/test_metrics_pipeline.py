from datetime import UTC, datetime, timedelta

from vanessa.core.messages import StoredMessage
from vanessa.knowledge.metrics.deterministic import DeterministicMetricsCalculator
from vanessa.knowledge.metrics.pipeline import MetricsPipeline
from vanessa.knowledge.metrics.pipeline_persist import persist_combined
from vanessa.knowledge.metrics.planner import MetricsPlanner
from vanessa.knowledge.metrics.retriever import MetricsRetriever, SenderProfile
from vanessa.knowledge.metrics.schema import Distance, MetricsSnapshot, PersonMetrics
from vanessa.knowledge.metrics.schema_clamp import clamp_int
from vanessa.knowledge.metrics.store import MetricsStore
from vanessa.knowledge.metrics.store_resolve import (
    fallback_person_id,
    id_from_display_name,
    id_from_telegram_index,
    valid_telegram_id,
)
from vanessa.knowledge.metrics.store_write import (
    log_snapshot_stored,
    snapshot_paths,
    zero_if_new,
)
from vanessa.knowledge.schema import VaultNote


def test_person_metrics_roundtrip_and_merge() -> None:
    raw = PersonMetrics.from_dict(
        {
            "valence": 2,
            "trust_score": "80",
            "distance": "friendly",
            "peak_hour": 25,
            "updated": "2026-09-01",
            "bogus": True,
        }
    )
    trust_score = 80
    peak_hour = 23
    assert raw.valence == 1.0
    assert raw.trust_score == trust_score
    assert raw.distance == Distance.FRIENDLY
    assert raw.peak_hour == peak_hour
    zero = PersonMetrics.zero()
    valence = 0.5
    merged = zero.merged(PersonMetrics(valence=valence, distance=None))
    assert merged.valence == valence
    assert merged.distance == Distance.NEUTRAL
    dumped = merged.with_updated("2026-09-08").to_dict()
    assert dumped["updated"] == "2026-09-08"
    assert PersonMetrics.from_dict("bad").valence is None
    assert clamp_int(None, 0, 10) is None
    assert clamp_int("x", 0, 10) is None
    assert clamp_int(-5, 0) == 0
    snap = MetricsSnapshot(person="ada", metrics=raw)
    assert snap.date == "2026-09-01"


def test_store_resolve_helpers() -> None:
    assert valid_telegram_id(None) is False
    assert valid_telegram_id(0) is False
    assert valid_telegram_id(3) is True
    index = {"telegram_id": {"3": {"id": "ada"}}, "aliases": {"ada": {"id": "ada"}}}
    assert id_from_telegram_index(index, 3) == "ada"
    assert id_from_telegram_index({}, 3) == ""
    assert id_from_display_name(index, "Ada") == "ada"
    assert id_from_display_name(index, None) == ""
    assert fallback_person_id({}, 99, None) == "user-99"
    assert snapshot_paths(None, created_card=True) == []
    assert "_index.yaml" in snapshot_paths("People/a.md", created_card=True)[1]
    log_snapshot_stored("ada", [])
    log_snapshot_stored("ada", ["People/ada.md"])
    valence = 0.2
    fresh = zero_if_new(
        MetricsSnapshot(person="ada", metrics=PersonMetrics(valence=valence)),
        None,
    )
    assert fresh.metrics.valence == valence
    same = zero_if_new(fresh, VaultNote("People/ada.md"))
    assert same is fresh


def test_deterministic_metrics_from_messages() -> None:
    start = datetime(2026, 9, 1, 12, tzinfo=UTC)
    sender_id = 7
    message_count = 2
    messages = [
        StoredMessage(
            id=1,
            role="assistant",
            content="hi",
            sender_telegram_id=None,
            created_at=start,
        ),
        StoredMessage(
            id=2,
            role="user",
            content="yo",
            sender_telegram_id=sender_id,
            created_at=start + timedelta(seconds=5),
        ),
        StoredMessage(
            id=3,
            role="user",
            content="again",
            sender_telegram_id=sender_id,
            created_at=start + timedelta(hours=2),
        ),
    ]
    result = DeterministicMetricsCalculator(history_days=14).compute_per_sender(messages)
    assert sender_id in result
    assert result[sender_id].message_count == message_count


class _Vault:
    def __init__(self, *, configured: bool = True) -> None:
        self.is_configured = configured
        self.notes: dict[str, VaultNote] = {}

    async def read_note(self, relative_path: str) -> VaultNote | None:
        return self.notes.get(relative_path)

    async def write_note(self, relative_path: str, meta: dict, body: str, **_k) -> str:
        self.notes[relative_path] = VaultNote(relative_path, meta, body)
        return relative_path


class _Index:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}
        self.rebuilt: list[str] = []

    async def load_folder(self, folder: str) -> dict:
        del folder
        return self.data

    async def rebuild_folder(self, folder: str) -> dict:
        self.rebuilt.append(folder)
        return {}


async def test_metrics_store_create_and_update() -> None:
    vault = _Vault()
    store = MetricsStore(vault, _Index())
    snap = MetricsSnapshot(
        person="ada",
        name="Ada",
        telegram_id=7,
        metrics=PersonMetrics(valence=0.1, message_count=3),
    )
    path = await store.store_snapshot(snap)
    assert path is not None
    loaded = await store.load_snapshot("ada")
    assert loaded is not None
    again = await store.store_snapshot(snap)
    assert again is not None
    assert await MetricsStore(_Vault(configured=False)).store_snapshot(snap) is None
    assert await store.load_snapshot("missing") is None
    vault.notes["People/empty.md"] = VaultNote("People/empty.md", meta={})
    assert await store.load_snapshot("empty") is None
    assert await store.resolve_by_telegram_id(0) == ""
    resolved = await store.resolve_by_telegram_id(7, name="Ada")
    assert resolved


async def test_metrics_pipeline_and_persist() -> None:
    MetricsPipeline._last_run = 0.0
    vault = _Vault()
    store = MetricsStore(vault, _Index({"telegram_id": {"7": {"id": "ada", "file": "People/ada.md"}}}))
    await store.store_snapshot(
        MetricsSnapshot(person="ada", telegram_id=7, metrics=PersonMetrics.zero())
    )

    class Planner:
        async def decide(self, transcript: str):
            del transcript
            return (
                MetricsSnapshot(
                    person="ada",
                    telegram_id=7,
                    name="Ada",
                    metrics=PersonMetrics(valence=0.4),
                ),
            )

    class Repo:
        async def get_messages_since(self, days: int):
            del days
            return [
                StoredMessage(
                    id=1,
                    role="user",
                    content="hi",
                    sender_telegram_id=7,
                    sender_name="Ada",
                    created_at=datetime(2026, 9, 1, tzinfo=UTC),
                )
            ]

    pipe = MetricsPipeline(store, Planner(), cooldown_seconds=0)
    stored = await pipe.run(Repo(), semantic=True)
    assert stored >= 0
    MetricsPipeline._last_run = 0.0
    disabled = MetricsPipeline(store, Planner(), enabled=False)
    assert await disabled.run(Repo()) == 0
    MetricsPipeline._last_run = 10**12
    cooled = MetricsPipeline(store, Planner(), cooldown_seconds=900)
    assert await cooled.run(Repo(), semantic=False) == 0

    class BoomPlanner:
        async def decide(self, transcript: str):
            del transcript
            raise RuntimeError("llm")

    MetricsPipeline._last_run = 0.0
    boom = MetricsPipeline(store, BoomPlanner(), cooldown_seconds=0)
    assert await boom.run(Repo(), semantic=True) >= 0
    stored_n, skipped = await persist_combined(
        store,
        {"ada": (7, "Ada", PersonMetrics(valence=0.4))},
    )
    assert stored_n + skipped >= 1


async def test_metrics_planner_parse() -> None:
    class LLM:
        async def complete(self, *_a, **_k) -> str:
            return '{"snapshots": [{"person": "Ada", "metrics": {"valence": 0.2}, "telegram_id": 7}, "x"]}'

    snaps = await MetricsPlanner(llm_client=LLM()).decide("hi")
    assert snaps[0].person == "Ada"

    class Bad:
        async def complete(self, *_a, **_k) -> str:
            return "nope"

    assert await MetricsPlanner(llm_client=Bad()).decide("x") == ()

    class ListPayload:
        async def complete(self, *_a, **_k) -> str:
            return "[]"

    assert await MetricsPlanner(llm_client=ListPayload()).decide("x") == ()


async def test_metrics_retriever_profiles() -> None:
    vault = _Vault()
    vault.notes["People/ada.md"] = VaultNote(
        "People/ada.md",
        meta={"metrics": {"valence": 0.1}, "mood": "calm"},
        body="## Контекст жизни\n- 2026-10-24: пишет бэкенд\n\n## Хроника\n- шум",
    )
    index = _Index({"telegram_id": {"7": {"id": "ada", "file": "People/ada.md"}}})
    retriever = MetricsRetriever(vault, index)
    profile = await retriever.get_by_telegram_id(7)
    assert profile is not None
    assert profile.facts == ("пишет бэкенд",)
    assert profile.display_name == "ada"
    assert await retriever.get_by_telegram_id(0) is None
    by_id = await retriever.get_by_person_id("ada")
    assert by_id is not None
    vr = await retriever.get_by_vrchat_name("Ada")
    assert vr is not None
    assert await retriever.get_by_vrchat_name("  ") is None
    empty = SenderProfile(person_id="x", metrics=None)
    assert empty.display_name == "x"
    assert await MetricsRetriever(_Vault(configured=False)).get_by_person_id("ada") is None
