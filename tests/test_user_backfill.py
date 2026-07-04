import pytest

from app.ingest.user_backfill import UserBackfillService, UserBackfillResult
from app.ingest.telegram_users import TelegramUserProfile


class FakeUow:
    async def commit(self) -> None:
        return None


class FakeMessageRepo:
    def __init__(self, sender_ids: list[int]) -> None:
        self._sender_ids = sender_ids

    async def get_distinct_sender_telegram_ids(self) -> list[int]:
        return self._sender_ids


class FakeUserRepo:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def upsert_profile(self, telegram_id: int, **kwargs):
        self.calls.append({"telegram_id": telegram_id, **kwargs})
        if telegram_id == 1:
            return object(), "created"
        if telegram_id == 2:
            return object(), "updated"
        return object(), "unchanged"


@pytest.mark.asyncio
async def test_user_backfill_service_counts_changes():
    service = UserBackfillService(
        messages=FakeMessageRepo([1, 2, 3]),
        users=FakeUserRepo(),
        unit_of_work=FakeUow(),
    )
    result = await service.run(
        nicknames={1: "Alice", 4: "Dave"},
        telegram_profiles={
            2: TelegramUserProfile(
                telegram_id=2,
                username="bob",
                first_name="Bob",
                last_name=None,
            )
        },
    )
    assert result == UserBackfillResult(
        sender_ids=4,
        created=1,
        updated=1,
        unchanged=2,
        telegram_fetched=1,
    )
