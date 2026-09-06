from vanessa.core.messages import StoredMessage

# Shared SELECT+JOIN for message rows that include a display name.
# WHERE/ORDER/LIMIT stay at each call site so query intent stays local.
JOINED_MESSAGE_SQL = """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
"""

JOINED_MESSAGE_WITH_REPLY_SQL = """
                SELECT m.id, m.sender_telegram_id, m.telegram_message_id,
                       m.role, m.content, m.qdrant_point_id, m.created_at,
                       m.reply_to_message_id, m.reply_to_text,
                       m.reply_to_sender_telegram_id, m.reply_to_sender_name,
                       m.attachments, m.photo_caption,
                       COALESCE(u.nickname, u.first_name, u.username) AS sender_name
                FROM messages m
                LEFT JOIN users u ON u.telegram_id = m.sender_telegram_id
"""


def row_to_stored(row) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        sender_telegram_id=row["sender_telegram_id"],
        telegram_message_id=row["telegram_message_id"],
        role=row["role"],
        content=row["content"],
        qdrant_point_id=row["qdrant_point_id"],
        created_at=row["created_at"],
        sender_name=row.get("sender_name"),
        reply_to_message_id=row.get("reply_to_message_id"),
        reply_to_text=row.get("reply_to_text"),
        reply_to_sender_telegram_id=row.get("reply_to_sender_telegram_id"),
        reply_to_sender_name=row.get("reply_to_sender_name"),
        attachments=row.get("attachments"),
        photo_caption=row.get("photo_caption"),
    )
