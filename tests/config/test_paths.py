from pathlib import Path

import pytest

from vanessa.config.content import (
    _merge_section_files,
    get_content,
    resolve_content_source,
)
from vanessa.config.paths import (
    repo_root,
    resolve_config_path,
    resolve_settings_path,
)
from vanessa.config.settings import settings


def test_repo_root_contains_config_tree() -> None:
    root = repo_root()
    assert (root / "config" / "behavior").is_dir()
    assert (root / "config" / "channels" / "telegram.yaml").is_file()


def test_resolve_config_path_keeps_existing(tmp_path: Path) -> None:
    target = tmp_path / "channels"
    target.mkdir()
    assert resolve_config_path(target) == target


def test_resolve_config_path_falls_back_to_repo() -> None:
    folder = resolve_config_path("config/channels")
    assert (folder / "vrchat.yaml").is_file()


def test_resolve_config_path_missing_stays_configured(tmp_path: Path) -> None:
    missing = tmp_path / "absent.yaml"
    assert resolve_config_path(missing) == missing


def test_empty_override_uses_config_root(monkeypatch) -> None:
    monkeypatch.setattr(settings, "config_root", "config")
    folder = resolve_settings_path("", "channels")
    assert (folder / "telegram.yaml").is_file()


def test_content_resolves() -> None:
    assert resolve_content_source().is_dir()


def test_behavior_split_files_exist() -> None:
    folder = repo_root() / "config" / "behavior"
    for name in (
        "compose/system.yaml",
        "compose/layout.yaml",
        "compose/notes.yaml",
        "compose/generation.yaml",
        "gate/planner.yaml",
        "gate/reaction_gate.yaml",
        "knowledge/mood.yaml",
    ):
        assert (folder / name).is_file()


def test_merged_sections_keep_both_jobs() -> None:
    content = get_content()
    assert content.llm.generation.planner.max_tokens > 0
    assert content.llm.task.strip()
    assert content.llm.context_header
    assert content.llm.owner_message_note.strip()
    assert "should_reply" in content.rag.planner_prompt
    assert "YES or NO" in content.decision.reaction_gate_prompt
    assert content.metrics.annoyance_note.strip()


def test_merge_rejects_duplicate_keys(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("foo: 1\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("foo: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate keys"):
        _merge_section_files(tmp_path, ("a.yaml", "b.yaml"))
