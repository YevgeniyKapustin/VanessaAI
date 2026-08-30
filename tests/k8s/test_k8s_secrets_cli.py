from pathlib import Path

import pytest

from scripts.k8s_secrets import main


def _write_env(path: Path, extra: str = "") -> Path:
    path.write_text(
        "TELEGRAM_BOT_TOKEN=tg-token\n"
        "POSTGRES_PASSWORD=pg-pass\n"
        "BROKER_REDIS_URL=redis://:pass@redis:6379/1\n"
        "DEEPSEEK_API_KEY=ds-key\n"
        "LOG_LEVEL=DEBUG\n"
        f"{extra}",
        encoding="utf-8",
    )
    return path


def test_cli_check_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    env = _write_env(tmp_path / ".env")
    assert main(["--from-env", str(env), "check"]) == 0
    out = capsys.readouterr().out
    assert "required: OK" in out
    assert "tg-token" not in out
    assert "LOG_LEVEL" not in out
    assert "TELEGRAM_BOT_TOKEN" in out


def test_cli_check_missing(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tg-token\n", encoding="utf-8")
    assert main(["--from-env", str(env), "check"]) == 2


def test_cli_example_prints_catalog(capsys: pytest.CaptureFixture[str]):
    assert main(["example"]) == 0
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN=" in out
    assert "poetry run python scripts/k8s_secrets.py apply" in out


def test_cli_apply_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _write_env(tmp_path / ".env")
    seen: list[str] = []

    def fake_kubectl(kubectl: str, document: str, *, dry_run: bool) -> None:
        seen.append(document)
        assert kubectl == "kubectl"
        assert dry_run is True
        assert "tg-token" not in document or "kind: Secret" in document
        if "kind: Secret" in document:
            assert "tg-token" in document
            assert "LOG_LEVEL" not in document

    monkeypatch.setattr("scripts.k8s_secrets._run_kubectl", fake_kubectl)
    code = main(
        [
            "--from-env",
            str(env),
            "apply",
            "--dry-run",
            "--broker-host",
            "host.docker.internal",
        ]
    )
    assert code == 0
    assert len(seen) == 2
    assert "host.docker.internal" in seen[0]
    assert "@redis:" not in seen[0]
    assert "kind: Secret" in seen[0]
    assert "kind: ConfigMap" in seen[1]
    assert "LOG_LEVEL" in seen[1]


def test_cli_apply_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _write_env(
        tmp_path / ".env",
        extra="REQUIRED_USER_TELEGRAM_ID=123456789\n",
    )
    seen: list[str] = []

    def fake_kubectl(kubectl: str, document: str, *, dry_run: bool) -> None:
        seen.append(document)
        assert dry_run is True
        assert "kind: ConfigMap" in document
        assert "REQUIRED_USER_TELEGRAM_ID" in document
        assert "tg-token" not in document
        assert "host.docker.internal" in document

    monkeypatch.setattr("scripts.k8s_secrets._run_kubectl", fake_kubectl)
    code = main(
        [
            "--from-env",
            str(env),
            "apply-config",
            "--dry-run",
            "--postgres-host",
            "host.docker.internal",
            "--qdrant-host",
            "host.docker.internal",
        ]
    )
    assert code == 0
    assert len(seen) == 1


def test_cli_apply_ensures_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    env = _write_env(tmp_path / ".env")
    seen: list[str] = []

    def fake_kubectl(kubectl: str, document: str, *, dry_run: bool) -> None:
        seen.append(document)
        assert dry_run is False

    monkeypatch.setattr("scripts.k8s_secrets._run_kubectl", fake_kubectl)
    code = main(
        [
            "--from-env",
            str(env),
            "--namespace",
            "vanessa",
            "apply",
            "--ensure-namespace",
        ]
    )
    assert code == 0
    assert len(seen) == 3
    assert "kind: Namespace" in seen[0]
    assert "name: vanessa-secrets" in seen[1]
    assert "kind: ConfigMap" in seen[2]


def test_cli_apply_skip_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env = _write_env(tmp_path / ".env")
    seen: list[str] = []

    def fake_kubectl(kubectl: str, document: str, *, dry_run: bool) -> None:
        seen.append(document)

    monkeypatch.setattr("scripts.k8s_secrets._run_kubectl", fake_kubectl)
    code = main(
        ["--from-env", str(env), "apply", "--dry-run", "--skip-config"]
    )
    assert code == 0
    assert len(seen) == 1
    assert "kind: Secret" in seen[0]
    assert "kind: ConfigMap" not in seen[0]


def test_cli_apply_refuses_missing_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tg-token\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise AssertionError("kubectl must not be called")

    monkeypatch.setattr("scripts.k8s_secrets._run_kubectl", boom)
    assert main(["--from-env", str(env), "apply"]) == 2


def test_cli_missing_env_file(tmp_path: Path):
    missing = tmp_path / "nope.env"
    with pytest.raises(SystemExit, match="env file not found"):
        main(["--from-env", str(missing), "check"])


def test_cli_check_merges_sibling_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    (tmp_path / ".env.defaults").write_text(
        "POSTGRES_PASSWORD=from-defaults\n"
        "BROKER_REDIS_URL=redis://:pass@redis:6379/0\n"
        "DEEPSEEK_API_KEY=ds-key\n",
        encoding="utf-8",
    )
    overlay = tmp_path / ".env.local"
    overlay.write_text("TELEGRAM_BOT_TOKEN=tg-token\n", encoding="utf-8")
    assert main(["--from-env", str(overlay), "check"]) == 0
    out = capsys.readouterr().out
    assert "required: OK" in out
    assert "from-defaults" not in out

