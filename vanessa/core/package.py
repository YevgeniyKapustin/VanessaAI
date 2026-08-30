from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, metadata
from pathlib import Path

_PACKAGE = "vanessa"
_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PackageInfo:
    name: str
    version: str
    description: str

    @property
    def api_title(self) -> str:
        label = self.name.replace("-", " ").replace("_", " ").title()
        return f"{label} API"


def package_info() -> PackageInfo:
    if (_REPO_ROOT / "pyproject.toml").is_file():
        return _from_pyproject()
    try:
        meta = metadata(_PACKAGE)
        return PackageInfo(
            name=str(meta["Name"] or _PACKAGE),
            version=str(meta["Version"] or "0.0.0"),
            description=str(meta.get("Summary") or ""),
        )
    except PackageNotFoundError:
        return PackageInfo(_PACKAGE, "0.0.0", "")


def package_version() -> str:
    return package_info().version


def _from_pyproject() -> PackageInfo:
    data = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    poetry = data.get("tool", {}).get("poetry", {})
    name = poetry.get("name")
    version = poetry.get("version")
    description = poetry.get("description")
    return PackageInfo(
        name=name if isinstance(name, str) and name else _PACKAGE,
        version=version if isinstance(version, str) and version else "0.0.0",
        description=description if isinstance(description, str) else "",
    )
