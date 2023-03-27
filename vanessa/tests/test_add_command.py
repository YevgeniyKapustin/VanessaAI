import pytest

from basic_actions.actions import send_text, send_file, send_stick, remove_msg
from tests.vars_for_test import chat_id, vk_error_100, Event, vk_error_15

text_commands = [
    ('теКст для теСта 1', 'теКст для теСта 1'),
    (1, 1),
    ('', vk_error_100),
]


@pytest.mark.parametrize('text, expect', text_commands)
def test_send_text(text, expect):
    assert send_text(chat_id, text) == expect
