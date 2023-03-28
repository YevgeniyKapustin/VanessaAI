from basic_actions.events import EventBuilder
from vars_for_test import MockEvent


def test_remove_from_shut_up_people():
    event = MockEvent
    assert (
        EventBuilder().set_msg(event.msg).set_chat_id(event.chat_id).
        get_event()
    )
