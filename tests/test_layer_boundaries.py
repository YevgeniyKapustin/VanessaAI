"""Inward-dependency rules between vanessa packages."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources(package_dir: Path) -> list[Path]:
    return [path for path in package_dir.rglob("*.py") if path.is_file()]


def _import_names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module]
    return []


def _nested_suites(node: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(node, ast.If):
        return [node.body, node.orelse]
    if isinstance(node, ast.Try):
        return [_try_suite(node)]
    if isinstance(node, ast.With):
        return [node.body]
    return []


def _collect_imported_names(nodes: list[ast.stmt], names: list[str]) -> None:
    for node in nodes:
        names.extend(_import_names(node))
        for suite in _nested_suites(node):
            _collect_imported_names(suite, names)


def _module_level_imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    _collect_imported_names(tree.body, names)
    return names


def _try_suite(node: ast.Try) -> list[ast.stmt]:
    suite = list(node.body)
    for handler in node.handlers:
        suite.extend(handler.body)
    suite.extend(node.orelse)
    suite.extend(node.finalbody)
    return suite


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
            "vanessa.pipeline.vision",
            "vanessa.infrastructure",
        ),
    )
