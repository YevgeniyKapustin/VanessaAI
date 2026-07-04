from datetime import datetime, timezone

import pytest

from app.ingest.telegram_export import (
    export_id_to_chat_id,
    flatten_text,
    parse_sender_id,
    parse_telegram_export,
)


def test_flatten_text_handles_entities(tmp_path):
    assert flatten_text("hello") == "hello"
    assert flatten_text([{"type": "bold", "text": "hi"}, " there"]) == "hi there"


def test_parse_sender_id():
    assert parse_sender_id("user123456789") == 123456789
    assert parse_sender_id(42) == 42
    assert parse_sender_id(None) is None


def test_export_id_to_chat_id_supergroup():
    assert export_id_to_chat_id("private_supergroup", 1234567890) == -1001234567890


def test_parse_telegram_export(tmp_path):
    export_file = tmp_path / "result.json"
    export_file.write_text(
        """
        {
          "name": "Test chat",
          "type": "private_supergroup",
          "id": 1234567890,
          "messages": [
            {
              "id": 10,
              "type": "service",
              "date": "2024-01-01T10:00:00"
            },
            {
              "id": 11,
              "type": "message",
              "date": "2024-01-01T10:01:00",
              "from": "Alice",
              "from_id": "user111",
              "text": "hello"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    metadata, messages = parse_telegram_export(export_file)
    assert metadata["name"] == "Test chat"
    assert len(messages) == 1
    assert messages[0].telegram_message_id == 11
    assert messages[0].sender_telegram_id == 111
    assert messages[0].sender_display_name == "Alice"
    assert messages[0].content == "hello"
    assert messages[0].created_at == datetime(2024, 1, 1, 10, 1, tzinfo=timezone.utc)


def test_extract_sender_names_from_export(tmp_path):
    export_file = tmp_path / "result.json"
    export_file.write_text(
        """
        {
          "messages": [
            {
              "id": 1,
              "type": "message",
              "from": "Alice",
              "from_id": "user111",
              "text": "hi"
            },
            {
              "id": 2,
              "type": "message",
              "from": "Alice",
              "from_id": "user111",
              "text": "again"
            },
            {
              "id": 3,
              "type": "service",
              "from": "Bob",
              "from_id": "user222"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    from app.ingest.telegram_export import extract_sender_names_from_export

    assert extract_sender_names_from_export(export_file) == {111: "Alice"}
