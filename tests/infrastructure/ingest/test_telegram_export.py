from datetime import UTC, datetime

from vanessa.infrastructure.ingest.telegram_export import (
    export_id_to_chat_id,
    extract_sender_names_from_export,
    flatten_text,
    parse_sender_id,
    parse_telegram_export,
)


def test_flatten_text_handles_entities(tmp_path):
    assert flatten_text("hello") == "hello"
    assert flatten_text([{"type": "bold", "text": "hi"}, " there"]) == "hi there"


def test_parse_sender_id():
    user_id = 123456789
    raw_id = 42
    assert parse_sender_id(f"user{user_id}") == user_id
    assert parse_sender_id(raw_id) == raw_id
    assert parse_sender_id(None) is None


def test_export_id_to_chat_id_supergroup():
    export_id = 1234567890
    assert export_id_to_chat_id("private_supergroup", export_id) == -1000000000000 - export_id


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
    telegram_message_id = 11
    sender_telegram_id = 111
    assert messages[0].telegram_message_id == telegram_message_id
    assert messages[0].sender_telegram_id == sender_telegram_id
    assert messages[0].sender_display_name == "Alice"
    assert messages[0].content == "hello"
    assert messages[0].created_at == datetime(2024, 1, 1, 10, 1, tzinfo=UTC)


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

    assert extract_sender_names_from_export(export_file) == {111: "Alice"}
