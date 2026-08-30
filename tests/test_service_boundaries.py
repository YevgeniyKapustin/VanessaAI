from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources(package: str) -> list[Path]:
    return list((ROOT / "services" / package).rglob("*.py"))


def test_bot_does_not_import_data_plane_or_siblings() -> None:
    forbidden = (
        "vanessa.knowledge",
        "vanessa.pipeline",
        "vanessa.infrastructure.db",
        "services.agent_core",
        "services.worker",
        "services.mcp",
    )
    for path in _python_sources("bot"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path}: {token}"


def test_worker_does_not_import_agent_core_or_bot() -> None:
    for path in _python_sources("worker"):
        text = path.read_text(encoding="utf-8")
        assert "services.agent_core" not in text, path
        assert "services.bot" not in text, path


def test_agent_core_does_not_import_worker_or_bot() -> None:
    for path in _python_sources("agent_core"):
        text = path.read_text(encoding="utf-8")
        assert "services.worker" not in text, path
        assert "services.bot" not in text, path
