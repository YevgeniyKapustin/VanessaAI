import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType
from aiogram.filters import CommandObject

from app.bot.container import BotServices
from app.bot.handlers.notes import create_notes_router
from app.bot.services.obsidian_notes import ObsidianNoteService
from app.config.content import get_content
from tests.bot.test_bot_message import make_telegram_message


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    readme = path / "README.md"
    readme.write_text("vault\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_save_note_writes_markdown(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _init_git_repo(vault)
    service = ObsidianNoteService(
        vault_path=str(vault),
        git_enabled=False,
    )

    saved = await service.save_note("hello from telegram")

    note_path = vault / saved.relative_path
    text = note_path.read_text(encoding="utf-8")
    assert "tags: [telegram, notes]" in text
    assert "hello from telegram" in text
    assert saved.filename.endswith(".md")


@pytest.mark.asyncio
async def test_save_note_with_attachment(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    service = ObsidianNoteService(
        vault_path=str(vault),
        git_enabled=False,
    )

    saved = await service.save_note(
        "with photo",
        attachment_bytes=b"fake-image",
        attachment_suffix=".png",
    )

    text = (vault / saved.relative_path).read_text(encoding="utf-8")
    assert "![[attachments/" in text
    assert ".png]]" in text
    attachments = list((vault / "attachments").iterdir())
    assert len(attachments) == 1
    assert attachments[0].read_bytes() == b"fake-image"


@pytest.mark.asyncio
async def test_save_note_commits_when_git_enabled(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _init_git_repo(vault)
    service = ObsidianNoteService(
        vault_path=str(vault),
        git_enabled=True,
    )
    service._run_git = MagicMock(
        side_effect=[
            MagicMock(stdout="", stderr=""),
            MagicMock(stdout="A telegram/x.md\n", stderr=""),
            MagicMock(stdout="", stderr=""),
            MagicMock(stdout="", stderr=""),
        ]
    )

    await service.save_note("commit me")

    commands = [call.args for call in service._run_git.call_args_list]
    assert commands[0][0] == "add"
    assert "commit" in commands[2]
    assert commands[3][0] == "push"


@pytest.mark.asyncio
async def test_cmd_note_rejects_non_owner_dm():
    message = make_telegram_message(text="/note hi", chat_type=ChatType.PRIVATE)
    message.answer = AsyncMock()
    message.photo = None
    access_guard = MagicMock()
    access_guard.ensure_owner_dm = MagicMock(
        return_value=get_content().bot.notes.owner_only.strip()
    )
    services = BotServices(
        chat_client=AsyncMock(),
        access_guard=access_guard,
        knowledge=AsyncMock(),
        texts=get_content().bot,
    )
    router = create_notes_router(services)
    handler = router.message.handlers[0].callback
    await handler(message, CommandObject(prefix="/", command="note", args="hi"))

    message.answer.assert_awaited_once_with(
        get_content().bot.notes.owner_only.strip()
    )


@pytest.mark.asyncio
async def test_cmd_note_saves_to_inbox_for_owner():
    message = make_telegram_message(text="/note buy milk", chat_type=ChatType.PRIVATE)
    message.from_user.id = 42
    message.answer = AsyncMock()
    message.photo = None
    access_guard = MagicMock()
    access_guard.ensure_owner_dm = MagicMock(return_value=None)
    knowledge = AsyncMock()
    knowledge.is_configured = True
    knowledge.ensure_structure = AsyncMock()
    knowledge.write_attachment = AsyncMock(return_value="inbox/attachments/x.jpg")
    knowledge.write_note = AsyncMock(return_value="inbox/2026-08-26_000000.md")
    services = BotServices(
        chat_client=AsyncMock(),
        access_guard=access_guard,
        knowledge=knowledge,
        texts=get_content().bot,
    )
    router = create_notes_router(services)
    handler = router.message.handlers[0].callback
    await handler(
        message,
        CommandObject(prefix="/", command="note", args="buy milk"),
    )

    knowledge.write_note.assert_awaited_once()
    args = knowledge.write_note.await_args.args
    assert args[0].startswith("inbox/")
    assert args[1]["type"] == "note"
    assert "buy milk" in args[2]
    assert "inbox/" in message.answer.await_args.args[0]
