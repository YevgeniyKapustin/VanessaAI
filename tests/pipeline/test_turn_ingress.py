from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vanessa.core.messages import StoredMessage
from vanessa.core.request_context import set_planning_started_signal
from vanessa.core.turn import ChatTurnInput
from vanessa.pipeline.orchestrator.orchestrator_config import OrchestratorConfig
from vanessa.pipeline.orchestrator.turn_ingress import (
    _turn_display_name,
    _TurnIngressMixin,
)


class _TrackingUsers:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.nickname = "Nick"
        self.first_name = "Ann"
        self.username = "ann"

    async def get_or_create(self, telegram_id: int, **kwargs) -> "_TrackingUsers":
        _ = kwargs
        self.calls.append(telegram_id)
        return self


class _RecordingMessages:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def create(self, **kwargs) -> StoredMessage:
        self.created.append(kwargs)
        return StoredMessage(
            id=1,
            role=str(kwargs["role"]),
            content=str(kwargs["content"]),
            sender_telegram_id=kwargs.get("sender_telegram_id"),
            channel=str(kwargs.get("channel") or "telegram"),
            sender_name=kwargs.get("sender_display_name"),
        )

    async def get_recent(
        self,
        limit: int = 50,
        *,
        channel: str = "telegram",
    ) -> list[StoredMessage]:
        _ = limit
        return [
            message
            for message in (
                StoredMessage(
                    id=1,
                    role="user",
                    content="x",
                    channel=str(item.get("channel") or "telegram"),
                )
                for item in self.created
            )
            if message.channel == channel
        ]


class _Ingress(_TurnIngressMixin):
    def __init__(self) -> None:
        self._users = _TrackingUsers()
        self._messages = _RecordingMessages()
        self._config = OrchestratorConfig(
            session_window_size=10,
            session_idle_seconds=300.0,
            post_reply_listen_count=5,
            planner_prefilter_enabled=False,
        )


@pytest.mark.asyncio
async def test_ingress_skips_get_or_create_without_telegram_id(monkeypatch):
    activity: list[tuple[int, int]] = []

    def fake_activity(user_id, chat_id) -> None:
        activity.append((user_id, chat_id))

    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.record_user_activity",
        fake_activity,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.ensure_people_alias_cache",
        AsyncMock(),
    )
    harness = _Ingress()
    turn = ChatTurnInput(
        telegram_chat_id=None,
        message="hello from vr",
        sender_telegram_id=None,
        sender_first_name="Alice",
        channel="vrchat",
    )
    ctx = await harness._prepare_incoming_context(turn)
    assert harness._users.calls == []
    assert activity == []
    created = harness._messages.created[0]
    assert created["channel"] == "vrchat"
    assert created["sender_display_name"]
    assert created["sender_telegram_id"] is None
    assert ctx.sender_name


@pytest.mark.asyncio
async def test_ingress_telegram_still_creates_user(monkeypatch):
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.record_user_activity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.ensure_people_alias_cache",
        AsyncMock(),
    )
    sender_id = 42
    harness = _Ingress()
    turn = ChatTurnInput(
        telegram_chat_id=-1001,
        message="hi",
        sender_telegram_id=sender_id,
        sender_first_name="Ann",
    )
    await harness._prepare_incoming_context(turn)
    assert harness._users.calls == [sender_id]
    created = harness._messages.created[0]
    assert created["channel"] == "telegram"
    assert created["sender_telegram_id"] == sender_id


def test_turn_display_name_prefers_explicit_attribute() -> None:
    turn = SimpleNamespace(
        sender_display_name="Ada",
        sender_first_name="Ann",
        sender_username="ann",
    )
    assert _turn_display_name(turn) == "Ada"


@pytest.mark.asyncio
async def test_vrchat_blank_name_falls_back_to_user(monkeypatch) -> None:
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.record_user_activity",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "vanessa.pipeline.orchestrator.turn_ingress.ensure_people_alias_cache",
        AsyncMock(),
    )
    harness = _Ingress()
    turn = ChatTurnInput(
        telegram_chat_id=None,
        message="...",
        sender_telegram_id=None,
        sender_first_name="",
        channel="vrchat",
    )
    ctx = await harness._prepare_incoming_context(turn)
    assert ctx.sender_name


@pytest.mark.asyncio
async def test_planning_started_signal_failure_is_swallowed() -> None:
    async def boom() -> None:
        raise RuntimeError("signal down")

    set_planning_started_signal(boom)
    try:
        await _Ingress()._notify_planning_started()
    finally:
        set_planning_started_signal(None)
