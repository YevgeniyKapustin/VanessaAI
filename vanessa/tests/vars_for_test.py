chat_id = 4

vk_error_100 = '[100] One of the parameters specified was missing or invalid: message is empty or invalid'
vk_error_15 = '[15] Access denied: message can not be deleted (admin message)'


class MockMsg:
    peer_id = 2000000004
    from_id = 465630601
    conversation_message_id = 4644
    text = 'текст'
    reply_message = None


class MockEvent:
    msg = MockMsg
    chat_id = chat_id
    attachments = None
