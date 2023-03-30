import pytest

from commands_logic.wiki import Wikipedia
from vars_for_test import MockEvent

question_commands = [
    'банан',
    'нига',
]


@pytest.mark.parametrize('question', question_commands)
def test_send_wiki_article(question):
    mock_event = MockEvent()
    mock_event.msg.text = f'что такое {question}'
    assert not Wikipedia(mock_event).send_wiki_article() == 'чота нету ничего'
