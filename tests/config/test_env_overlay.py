from pathlib import Path

from vanessa.config.env_overlay import (
    build_local_overlay,
    prepare_local_overlay,
    render_overlay,
)


def test_build_local_overlay_keeps_secrets_and_diffs():
    defaults = {
        "POSTGRES_PASSWORD": "vanessa",
        "COMPOSE_FILE": "a.yml:b.yml",
    }
    legacy = {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "POSTGRES_PASSWORD": "vanessa",
        "WEB_SEARCH_ENABLED": "false",
        "VISION_PHOTO_PLACEHOLDER": "[фото]",
        "ANTHROPIC_API_KEY": "sk-ant",
        "DEEPSEEK_API_KEY": "your_deepseek_api_key",
        "ALLOWED_CHAT_TELEGRAM_ID": "-1001",
    }
    overlay = build_local_overlay(defaults, legacy, windows=False)
    assert overlay["TELEGRAM_BOT_TOKEN"] == "123:abc"
    assert overlay["WEB_SEARCH_ENABLED"] == "false"
    assert overlay["ALLOWED_CHAT_TELEGRAM_ID"] == "-1001"
    assert "POSTGRES_PASSWORD" not in overlay
    assert "VISION_PHOTO_PLACEHOLDER" not in overlay
    assert "ANTHROPIC_API_KEY" not in overlay
    assert "DEEPSEEK_API_KEY" not in overlay
    assert overlay["WORKER_ENABLED"] == "true"
    assert "COMPOSE_FILE" not in overlay


def test_windows_compose_file_uses_semicolons():
    defaults = {"COMPOSE_FILE": "a.yml:b.yml"}
    overlay = build_local_overlay(defaults, {}, windows=True)
    assert overlay["COMPOSE_FILE"] == "a.yml;b.yml"


def test_claude_keeps_anthropic_key():
    overlay = build_local_overlay(
        {},
        {"LLM_PROVIDER": "claude", "ANTHROPIC_API_KEY": "sk-ant"},
        windows=False,
    )
    assert overlay["ANTHROPIC_API_KEY"] == "sk-ant"
    assert overlay["LLM_PROVIDER"] == "claude"


def test_prepare_local_overlay_reads_files(tmp_path: Path):
    (tmp_path / ".env.defaults").write_text("FOO=bar\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\n", encoding="utf-8")
    overlay, dest = prepare_local_overlay(tmp_path, windows=False)
    assert overlay["TELEGRAM_BOT_TOKEN"] == "tok"
    assert dest == tmp_path / ".env.local"
    text = render_overlay(overlay)
    assert "TELEGRAM_BOT_TOKEN=tok" in text
