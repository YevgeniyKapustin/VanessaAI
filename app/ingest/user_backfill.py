from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.protocols import UnitOfWorkProtocol
from app.db.repository import MessageRepository, UserRepository
from app.ingest.telegram_users import TelegramUserProfile


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
        raise ValueError(f"Nicknames file must be a mapping: {path}")
    return {int(key): str(value).strip() for key, value in raw.items() if str(value).strip()}


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
        sender_ids = set(await self._messages.get_distinct_sender_telegram_ids())
        sender_ids.update(nicknames)
        sender_ids.update(telegram_profiles)
        sender_ids.update(export_names)

        created = 0
        updated = 0
        unchanged = 0

        for telegram_id in sorted(sender_ids):
            profile = telegram_profiles.get(telegram_id)
            export_name = export_names.get(telegram_id)
            _, change = await self._users.upsert_profile(
                telegram_id,
                username=profile.username if profile else None,
                first_name=(
                    profile.first_name if profile and profile.first_name else export_name
                ),
                last_name=profile.last_name if profile else None,
                nickname=nicknames.get(telegram_id),
                force_nickname=force_nicknames,
            )
            if change == "created":
                created += 1
            elif change == "updated":
                updated += 1
            else:
                unchanged += 1

        await self._uow.commit()
        return UserBackfillResult(
            sender_ids=len(sender_ids),
            created=created,
            updated=updated,
            unchanged=unchanged,
            telegram_fetched=len(telegram_profiles),
        )
