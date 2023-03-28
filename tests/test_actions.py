import pytest

from basic_actions.actions import send_text, send_file, send_stick, remove_msg
from tests.vars_for_test import chat_id, vk_error_100, vk_error_15

text_commands = [
    ('теКст для теСта 1', 'теКст для теСта 1'),
    (1, 1),
    ('', vk_error_100),
]


class MockMsg:
    peer_id = 2000000004
    from_id = 465630601
    conversation_message_id = 4644
    text = 'добавить команду текст биба: и боба'
    reply_message = None


class MockEvent:
    msg = MockMsg
    chat_id = chat_id
    attachments = None


@pytest.mark.parametrize('text, expect', text_commands)
def test_send_text(text, expect):
    assert send_text(chat_id, text) == expect


file_commands = [
    ('doc465630601_633778583', 'doc465630601_633778583'),
    ('photo-212138773_457239022', 'photo-212138773_457239022'),
    ('', vk_error_100),
]


@pytest.mark.parametrize('url, expect', file_commands)
def test_send_file(url, expect):
    assert send_file(chat_id, url) == expect


stick_commands = [
    (18509, 18509),
    ('9050', '9050'),
    ('', None),
]


@pytest.mark.parametrize('stick_id, expect', stick_commands)
def test_send_stick(stick_id, expect):
    assert send_stick(chat_id, stick_id) == expect


remove_commands = [
    (MockEvent, vk_error_15),
]


@pytest.mark.parametrize('event, expect', remove_commands)
def test_remove_msg(event, expect):
    assert remove_msg(event) == expect
