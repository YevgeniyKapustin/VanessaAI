from basic_actions.events import EventBuilder
from vars_for_test import MockEvent


def test_building_event():
    event = MockEvent
    assert (
        EventBuilder().set_msg(event.msg).set_chat_id(event.chat_id).
        get_event()
    )
