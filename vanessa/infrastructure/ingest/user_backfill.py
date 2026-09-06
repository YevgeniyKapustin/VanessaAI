from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from vanessa.core.protocols import UnitOfWorkProtocol
from vanessa.infrastructure.db.repository import MessageRepository, UserRepository
from vanessa.infrastructure.ingest.telegram_users import TelegramUserProfile


@dataclass(frozen=True, slots=True)
class UserBackfillResult:
    sender_ids: int
    created: int
    updated: int
    unchanged: int
    telegram_fetched: int


def load_nicknames(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise TypeError(f"Nicknames file must be a mapping: {path}")
    return {int(key): str(value).strip() for key, value in raw.items() if str(value).strip()}


def _merge_sender_ids(
    message_ids: list[int],
    nicknames: dict[int, str],
    telegram_profiles: dict[int, TelegramUserProfile],
    export_names: dict[int, str],
) -> set[int]:
    sender_ids = set(message_ids)
    sender_ids.update(nicknames)
    sender_ids.update(telegram_profiles)
    sender_ids.update(export_names)
    return sender_ids


def _profile_names(
    profile: TelegramUserProfile | None,
    export_name: str | None,
) -> tuple[str | None, str | None, str | None]:
    if profile is None:
        return None, export_name, None
    first_name = profile.first_name if profile.first_name else export_name
    return profile.username, first_name, profile.last_name


def _count_change(
    change: str, created: int, updated: int, unchanged: int
) -> tuple[int, int, int]:
    if change == "created":
        return created + 1, updated, unchanged
    if change == "updated":
        return created, updated + 1, unchanged
    return created, updated, unchanged + 1


class UserBackfillService:
    def __init__(
        self,
        messages: MessageRepository,
        users: UserRepository,
        unit_of_work: UnitOfWorkProtocol,
    ) -> None:
        self._messages = messages
        self._users = users
        self._uow = unit_of_work

    async def run(
        self,
        *,
        nicknames: dict[int, str] | None = None,
        telegram_profiles: dict[int, TelegramUserProfile] | None = None,
        export_names: dict[int, str] | None = None,
        force_nicknames: bool = False,
    ) -> UserBackfillResult:
        nicknames = nicknames or {}
        telegram_profiles = telegram_profiles or {}
        export_names = export_names or {}
        sender_ids = _merge_sender_ids(
            await self._messages.get_distinct_sender_telegram_ids(),
            nicknames,
            telegram_profiles,
            export_names,
        )
        created, updated, unchanged = await self._upsert_senders(
            sender_ids,
            nicknames,
            telegram_profiles,
            export_names,
            force_nicknames=force_nicknames,
        )
        await self._uow.commit()
        return UserBackfillResult(
            sender_ids=len(sender_ids),
            created=created,
            updated=updated,
            unchanged=unchanged,
            telegram_fetched=len(telegram_profiles),
        )

    async def _upsert_senders(
        self,
        sender_ids: set[int],
        nicknames: dict[int, str],
        telegram_profiles: dict[int, TelegramUserProfile],
        export_names: dict[int, str],
        *,
        force_nicknames: bool,
    ) -> tuple[int, int, int]:
        created = 0
        updated = 0
        unchanged = 0
        for telegram_id in sorted(sender_ids):
            username, first_name, last_name = _profile_names(
                telegram_profiles.get(telegram_id),
                export_names.get(telegram_id),
            )
            _, change = await self._users.upsert_profile(
                telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                nickname=nicknames.get(telegram_id),
                force_nickname=force_nicknames,
            )
            created, updated, unchanged = _count_change(
                change, created, updated, unchanged
            )
        return created, updated, unchanged
