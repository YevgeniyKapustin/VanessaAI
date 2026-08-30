"""Inward-dependency rules between vanessa packages."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources(package_dir: Path) -> list[Path]:
    return [path for path in package_dir.rglob("*.py") if path.is_file()]


def _module_level_imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []

    def collect(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.If):
                collect(node.body)
                collect(node.orelse)
            elif isinstance(node, ast.Try):
                collect(node.body)
                for handler in node.handlers:
                    collect(handler.body)
                collect(node.orelse)
                collect(node.finalbody)
            elif isinstance(node, ast.With):
                collect(node.body)

    collect(tree.body)
    return names


def _forbidden_hits(imported: list[str], prefixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for name in imported:
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                hits.append(name)
                break
    return hits


def _assert_no_forbidden(package_dir: Path, forbidden: tuple[str, ...]) -> None:
    for path in _python_sources(package_dir):
        hits = _forbidden_hits(_module_level_imported_names(path), forbidden)
        assert hits == [], f"{path.relative_to(ROOT)}: {hits}"


def test_core_does_not_import_outer_layers() -> None:
    _assert_no_forbidden(
        ROOT / "vanessa" / "core",
        (
            "vanessa.knowledge",
            "vanessa.pipeline",
            "vanessa.infrastructure",
        ),
    )


def test_decision_does_not_import_llm_or_infra() -> None:
    _assert_no_forbidden(
        ROOT / "vanessa" / "pipeline" / "decision",
        (
            "vanessa.pipeline.llm",
            "vanessa.pipeline.rag",
            "vanessa.infrastructure",
        ),
    )
