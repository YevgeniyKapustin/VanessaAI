from commands_logic.mute import Mute
from test_actions import MockEvent


def test_shut_up():
    mock_event = MockEvent()
    mock_event.msg.text = 'мут'
    assert Mute(mock_event).shut_up() == 'жертвы нету в этой беседе'


def test_redemption():
    assert Mute(MockEvent()).shut_up() == 'жертвы нету в этой беседе'
