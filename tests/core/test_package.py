from importlib.metadata import PackageNotFoundError
from pathlib import Path

import tomllib

from vanessa.core import package as package_mod
from vanessa.core.package import package_info, package_version

_ROOT = Path(__file__).resolve().parents[2]


def _poetry() -> dict:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["poetry"]


def test_package_info_matches_pyproject() -> None:
    poetry = _poetry()
    info = package_info()
    assert info.version == poetry["version"]
    assert info.name == poetry["name"]
    assert info.description == poetry["description"]
    assert info.api_title == "Vanessa API"


def test_package_version_matches_pyproject() -> None:
    assert package_version() == _poetry()["version"]


def test_metadata_when_pyproject_missing(monkeypatch) -> None:
    class FakeMeta(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    fake = FakeMeta(
        Name="vanessa",
        Version="1.2.3",
        Summary="from dist",
    )
    monkeypatch.setattr(
        package_mod,
        "_REPO_ROOT",
        Path("/nonexistent"),
    )
    monkeypatch.setattr(package_mod, "metadata", lambda _name: fake)
    info = package_info()
    assert info.version == "1.2.3"
    assert info.description == "from dist"


def test_empty_info_when_nothing_available(monkeypatch) -> None:
    monkeypatch.setattr(package_mod, "_REPO_ROOT", Path("/nonexistent"))

    def missing(_name: str):
        raise PackageNotFoundError(_name)

    monkeypatch.setattr(package_mod, "metadata", missing)
    info = package_info()
    assert info.version == "0.0.0"
    assert info.name == "vanessa"
