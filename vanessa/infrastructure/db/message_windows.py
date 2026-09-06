from sqlalchemy import text

from vanessa.core.messages import RAG_SOURCE_ROLE, StoredMessage
from vanessa.infrastructure.db.message_rows import JOINED_MESSAGE_SQL, row_to_stored

_BEFORE_SQL = (
    JOINED_MESSAGE_SQL
    + """
                    WHERE m.role = 'user'
                      AND (m.created_at, m.id) < (:created_at, :anchor_id)
                    ORDER BY m.created_at DESC, m.id DESC
                    LIMIT :limit
                    """
)

_CENTER_SQL = (
    JOINED_MESSAGE_SQL
    + """
                WHERE m.id = :anchor_id
                """
)

_AFTER_SQL = (
    JOINED_MESSAGE_SQL
    + """
                    WHERE m.role = 'user'
                      AND (m.created_at, m.id) > (:created_at, :anchor_id)
                    ORDER BY m.created_at ASC, m.id ASC
                    LIMIT :limit
                    """
)


async def _load_before(
    session,
    anchor: StoredMessage,
    anchor_id: int,
    before: int,
) -> list[StoredMessage]:
    if before <= 0:
        return []
    result = await session.execute(
        text(_BEFORE_SQL),
        {
            "created_at": anchor.created_at,
            "anchor_id": anchor_id,
            "limit": before,
        },
    )
    return [row_to_stored(row) for row in reversed(result.mappings().all())]


async def _load_center(session, anchor_id: int) -> list[StoredMessage]:
    anchor_row = await session.execute(text(_CENTER_SQL), {"anchor_id": anchor_id})
    anchor_message = anchor_row.mappings().first()
    if anchor_message is None:
        return []
    return [row_to_stored(anchor_message)]


async def _load_after(
    session,
    anchor: StoredMessage,
    anchor_id: int,
    after: int,
) -> list[StoredMessage]:
    if after <= 0:
        return []
    result = await session.execute(
        text(_AFTER_SQL),
        {
            "created_at": anchor.created_at,
            "anchor_id": anchor_id,
            "limit": after,
        },
    )
    return [row_to_stored(row) for row in result.mappings().all()]


async def _window_for_anchor(
    self,
    anchor_id: int,
    before: int,
    after: int,
) -> list[StoredMessage]:
    anchor = await self.get_by_id(anchor_id)
    if anchor is None or anchor.created_at is None or anchor.role != RAG_SOURCE_ROLE:
        return []

    before_rows = await _load_before(self._session, anchor, anchor_id, before)
    center = await _load_center(self._session, anchor_id)
    if not center:
        return before_rows
    after_rows = await _load_after(self._session, anchor, anchor_id, after)
    return before_rows + center + after_rows


async def _anchor_only_blocks(
    repo, anchor_ids: list[int]
) -> list[tuple[int, list[StoredMessage]]]:
    messages = await repo.get_by_ids(anchor_ids)
    return [
        (message.id, [message])
        for message in messages
        if message.role == RAG_SOURCE_ROLE
    ]


def _trim_window(window: list[StoredMessage], remaining: int) -> list[StoredMessage]:
    if len(window) > remaining:
        return window[:remaining]
    return window


async def _collect_window_blocks(
    repo,
    anchor_ids: list[int],
    before: int,
    after: int,
    max_total: int,
) -> list[tuple[int, list[StoredMessage]]]:
    blocks: list[tuple[int, list[StoredMessage]]] = []
    total = 0
    for anchor_id in anchor_ids:
        if total >= max_total:
            break
        window = await repo._window_for_anchor(anchor_id, before, after)
        if not window:
            continue
        window = _trim_window(window, max_total - total)
        blocks.append((anchor_id, window))
        total += len(window)
    return blocks


async def get_conversation_window_blocks(
    self,
    anchor_ids: list[int],
    before: int = 10,
    after: int = 10,
    max_total: int = 80,
) -> list[tuple[int, list[StoredMessage]]]:
    if not anchor_ids:
        return []
    if before <= 0 and after <= 0:
        return await _anchor_only_blocks(self, anchor_ids)
    return await _collect_window_blocks(self, anchor_ids, before, after, max_total)
