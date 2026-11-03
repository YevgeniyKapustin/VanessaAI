from pathlib import Path
from types import SimpleNamespace

from services.worker.announce import registry
from services.worker.announce.registry import build_announcers, load_specs

WATCH = """
id: deploy
kind: deploy
enabled_env: DEPLOY_WATCH_ENABLED
chat_id_env: DEPLOY_CHAT_ID
url_env: DEPLOY_BRIDGE_URL
token_env: DEPLOY_BRIDGE_TOKEN
path: /deploy/latest
state_key: vanessa:deploy_last_job
header: "На прод выкатили в {when}"
task: TASK
"""


class FakeState:
    def __init__(self) -> None:
        self.key: int | None = None

    async def last(self) -> int | None:
        return self.key

    async def remember(self, event_id: int) -> None:
        self.key = event_id


class FakeBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, stream: str, message) -> None:
        self.published.append((stream, message))

    def announce_state(self, key: str) -> FakeState:
        self.last_key = key
        return FakeState()


class FakeComposer:
    async def compose(self, *_args, **_kwargs) -> str:
        return "text"


def _settings(**overrides):
    base = {
        "deploy_watch_enabled": True,
        "deploy_bridge_url": "http://host.docker.internal:8643",
        "deploy_bridge_token": "secret",
        "deploy_chat_id": -1000000000001,
        "deploy_probe_url": "https://prod.example/api/auth/methods",
        "deploy_rollout_url": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _dir(tmp_path: Path, text: str = WATCH) -> Path:
    folder = tmp_path / "announce"
    folder.mkdir(exist_ok=True)
    (folder / "deploy.yaml").write_text(text, encoding="utf-8")
    return folder


async def test_shipped_watch_config_parses() -> None:
    specs = {spec.id: spec for spec in load_specs()}

    assert "deploy" in specs
    assert specs["deploy"].kind == "deploy"
    assert specs["deploy"].mention is True


def test_enabled_and_configured_watch_builds_one_loop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(registry, "_composer", lambda *_: FakeComposer())
    broker = FakeBroker()

    loops = build_announcers(
        broker, _settings(), outbound_stream="out", directory=_dir(tmp_path)
    )

    assert [loop.spec.id for loop in loops] == ["deploy"]
    assert broker.last_key == "vanessa:deploy_last_job"


def test_disabled_watch_builds_no_loop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(registry, "_composer", lambda *_: FakeComposer())

    assert build_announcers(
        FakeBroker(),
        _settings(deploy_watch_enabled=False),
        outbound_stream="out",
        directory=_dir(tmp_path),
    ) == []


def test_missing_env_settings_build_no_loop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(registry, "_composer", lambda *_: FakeComposer())
    for name in ("deploy_bridge_url", "deploy_chat_id"):
        assert build_announcers(
            FakeBroker(),
            _settings(**{name: ""}),
            outbound_stream="out",
            directory=_dir(tmp_path),
        ) == []


def test_unknown_kind_builds_no_loop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(registry, "_composer", lambda *_: FakeComposer())

    assert build_announcers(
        FakeBroker(),
        _settings(),
        outbound_stream="out",
        directory=_dir(tmp_path, WATCH.replace("kind: deploy", "kind: telegram")),
    ) == []


def test_empty_directory_builds_nothing() -> None:
    assert load_specs(Path("nowhere")) == []
