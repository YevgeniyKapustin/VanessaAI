import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class SavedNote:
    relative_path: str
    filename: str


@dataclass(frozen=True, slots=True)
class CompletedGit:
    stdout: str
    stderr: str


class ObsidianNoteService:
    def __init__(
        self,
        vault_path: str | None = None,
        notes_subdir: str | None = None,
        attachments_subdir: str | None = None,
        git_enabled: bool | None = None,
        git_remote: str | None = None,
        git_branch: str | None = None,
        git_user_name: str | None = None,
        git_user_email: str | None = None,
    ) -> None:
        raw = vault_path if vault_path is not None else settings.obsidian_vault_path
        self._vault_path = Path(raw.strip()) if raw.strip() else None
        self._notes_subdir = notes_subdir or settings.obsidian_notes_subdir
        self._attachments_subdir = (
            attachments_subdir or settings.obsidian_attachments_subdir
        )
        self._git_enabled = (
            settings.obsidian_git_enabled if git_enabled is None else git_enabled
        )
        self._git_remote = git_remote or settings.obsidian_git_remote
        self._git_branch = (
            git_branch if git_branch is not None else settings.obsidian_git_branch
        )
        self._git_user_name = git_user_name or settings.obsidian_git_user_name
        self._git_user_email = git_user_email or settings.obsidian_git_user_email
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        return self._vault_path is not None and self._vault_path.is_dir()

    async def save_note(
        self,
        text: str,
        *,
        attachment_bytes: bytes | None = None,
        attachment_suffix: str = ".jpg",
    ) -> SavedNote:
        if not self.is_configured or self._vault_path is None:
            raise RuntimeError("obsidian vault is not configured")

        async with self._lock:
            return await asyncio.to_thread(
                self._save_note_sync,
                text,
                attachment_bytes,
                attachment_suffix,
            )

    def _save_note_sync(
        self,
        text: str,
        attachment_bytes: bytes | None,
        attachment_suffix: str,
    ) -> SavedNote:
        assert self._vault_path is not None
        now = datetime.now(timezone.utc).astimezone()
        stamp = now.strftime("%Y-%m-%d_%H%M%S")
        filename = f"{stamp}.md"
        notes_dir = self._vault_path / self._notes_subdir
        notes_dir.mkdir(parents=True, exist_ok=True)
        note_path = notes_dir / filename

        body_parts: list[str] = []
        cleaned = text.strip()
        if cleaned:
            body_parts.append(cleaned)

        staged = [note_path.relative_to(self._vault_path).as_posix()]
        if attachment_bytes:
            attachment_name = self._write_attachment(
                stamp,
                attachment_bytes,
                attachment_suffix,
            )
            attachment_rel = f"{self._attachments_subdir}/{attachment_name}"
            staged.append(attachment_rel)
            body_parts.append(f"![[{attachment_rel}]]")

        body = "\n\n".join(body_parts).strip()
        content = (
            "---\n"
            f"date: {now.date().isoformat()}\n"
            "tags: [telegram, notes]\n"
            "---\n\n"
            f"{body}\n"
        )
        note_path.write_text(content, encoding="utf-8")
        relative = staged[0]

        if self._git_enabled:
            self._git_commit_and_push(staged)

        logger.info("obsidian_note_saved path=%s", relative)
        return SavedNote(relative_path=relative, filename=filename)

    def _write_attachment(
        self,
        stamp: str,
        data: bytes,
        suffix: str,
    ) -> str:
        assert self._vault_path is not None
        safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        name = f"{stamp}{_sanitize_name(safe_suffix)}"
        attachments_dir = self._vault_path / self._attachments_subdir
        attachments_dir.mkdir(parents=True, exist_ok=True)
        path = attachments_dir / name
        path.write_bytes(data)
        return name

    def _git_commit_and_push(self, relative_paths: list[str]) -> None:
        self._run_git("add", "--", *relative_paths)
        status = self._run_git("status", "--porcelain")
        if not status.stdout.strip():
            return
        message = f"note: {Path(relative_paths[0]).name}"
        self._run_git(
            "-c",
            f"user.name={self._git_user_name}",
            "-c",
            f"user.email={self._git_user_email}",
            "commit",
            "-m",
            message,
        )
        branch = self._git_branch.strip()
        if branch:
            self._run_git("push", self._git_remote, branch)
        else:
            self._run_git("push", self._git_remote)

    def _run_git(self, *args: str) -> CompletedGit:
        assert self._vault_path is not None
        result = subprocess.run(
            ["git", *args],
            cwd=self._vault_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "git failed").strip()
            raise RuntimeError(detail)
        return CompletedGit(stdout=result.stdout, stderr=result.stderr)


def _sanitize_name(value: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", value.strip())
    return cleaned or ".bin"
