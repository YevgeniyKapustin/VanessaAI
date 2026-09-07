from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources(package: str) -> list[Path]:
    return list((ROOT / "services" / package).rglob("*.py"))


def test_presence_does_not_import_data_plane_or_siblings() -> None:
    forbidden = (
        "vanessa.knowledge",
        "vanessa.pipeline",
        "vanessa.infrastructure.db",
        "services.agent",
        "services.worker",
        "services.mcp",
        "services.bot",
    )
    for path in _python_sources("presence"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path}: {token}"
