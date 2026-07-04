import pytest

from app.core.messages import ContextMessage
from app.decision.gate.bot_names import text_mentions_bot_name
from app.decision.gate.user_ignore import (
    ChatIgnoreRegistry,
    apply_owner_ignore_command,
    is_ignore_user_command,
    resolve_ignore_target,
)
from app.decision.detectors.intent import IntentDetector


def test_text_mentions_inflected_bot_name():
    names = ("ванесса", "vanessa")
    assert text_mentions_bot_name("ванессе игнорируй его", names) is True
    assert text_mentions_bot_name("привет всем", names) is False


def test_intent_detects_inflected_vanessa():
    detector = IntentDetector(bot_names=("ванесса",))
    result = detector.detect("ванессе игнорируй его")
    assert result.mentions_bot is True


def test_ignore_registry_tracks_users():
    registry = ChatIgnoreRegistry()
    registry.ignore(-100, 42)
    assert registry.is_ignored(-100, 42) is True
    assert registry.is_ignored(-100, 99) is False
    registry.unignore(-100, 42)
    assert registry.is_ignored(-100, 42) is False


def test_resolve_ignore_target_from_reply():
    target = resolve_ignore_target(
        "игнорируй его",
        [],
        reply_to_sender_id=99,
        owner_id=1,
    )
    assert target == 99


def test_apply_owner_ignore_command_registers_target():
    registry = ChatIgnoreRegistry()
    recent = [
        ContextMessage(id=1, role="user", content="где", sender_telegram_id=99),
    ]
    applied = apply_owner_ignore_command(
        registry,
        chat_id=-100,
        owner_id=1,
        sender_id=1,
        text="ванессе игнорируй его",
        recent_messages=recent,
        reply_to_sender_id=99,
    )
    assert applied is True
    assert registry.is_ignored(-100, 99) is True


def test_is_ignore_user_command():
    assert is_ignore_user_command("ванессе игнорируй его") is True
    assert is_ignore_user_command("расскажи про меш") is False
