from app.core.messages import StoredMessage, stored_block_to_context


def test_stored_block_to_context_skips_assistant_messages():
    block = stored_block_to_context(
        2,
        [
            StoredMessage(id=1, role="user", content="вопрос"),
            StoredMessage(id=2, role="assistant", content="старый ответ бота"),
            StoredMessage(id=3, role="user", content="ещё вопрос"),
        ],
    )

    assert block is not None
    assert block.anchor_id == 3
    assert [message.id for message in block.messages] == [1, 3]
    assert all(message.role == "user" for message in block.messages)


def test_stored_block_to_context_returns_none_without_user_messages():
    assert stored_block_to_context(
        1,
        [StoredMessage(id=1, role="assistant", content="только бот")],
    ) is None
