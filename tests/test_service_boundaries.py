from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources(package: str) -> list[Path]:
    return list((ROOT / "services" / package).rglob("*.py"))


def test_bot_does_not_import_data_plane_or_siblings() -> None:
    forbidden = (
        "vanessa.knowledge",
        "vanessa.pipeline",
        "vanessa.infrastructure.db",
        "services.agent",
        "services.worker",
        "services.mcp",
    )
    for path in _python_sources("bot"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path}: {token}"


def test_worker_does_not_import_agent_or_bot() -> None:
    for path in _python_sources("worker"):
        text = path.read_text(encoding="utf-8")
        assert "services.agent" not in text, path
        assert "services.bot" not in text, path


def test_agent_does_not_import_worker_or_bot() -> None:
    for path in _python_sources("agent"):
        text = path.read_text(encoding="utf-8")
        assert "services.worker" not in text, path
        assert "services.bot" not in text, path


def test_agent_has_no_http_chat_route() -> None:
    chat_route = ROOT / "services" / "agent" / "routes" / "chat.py"
    assert not chat_route.exists()


def test_agent_has_no_http_notes_route() -> None:
    notes_route = ROOT / "services" / "agent" / "routes" / "notes.py"
    assert not notes_route.exists()


def test_knowledge_does_not_import_pipeline() -> None:
    root = ROOT / "vanessa" / "knowledge"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "vanessa.pipeline" not in text, path
