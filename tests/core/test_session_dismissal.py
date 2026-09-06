from vanessa.core.messages import ContextMessage
from vanessa.core.session import (
    build_chat_session_state,
    in_post_reply_listen_window,
    is_dismissal_request,
)


def test_dismissal_detects_stop_phrases():
    assert is_dismissal_request("ванесса хватит") is True
    assert is_dismissal_request("перестань отвечать") is True
    assert is_dismissal_request("закрой контекст") is True
    assert is_dismissal_request("хватит") is True
    assert is_dismissal_request("да всё сгинь") is True
    assert is_dismissal_request("уйди, закрой сессию") is True


def test_dismissal_allows_normal_messages():
    assert is_dismissal_request("расскажи про меш") is False
    assert is_dismissal_request("хватит ли памяти") is False
    assert is_dismissal_request("") is False
    assert is_dismissal_request("   ") is False


def test_listen_window_closes_on_dismissal():
    recent = [
        ContextMessage(id=1, role="assistant", content="ok"),
        ContextMessage(id=2, role="user", content="хватит"),
    ]
    assert in_post_reply_listen_window(recent, max_messages=3) is False


def test_listen_window_stays_open_for_follow_up():
    recent = [
        ContextMessage(id=1, role="assistant", content="ok"),
        ContextMessage(id=2, role="user", content="а дальше?"),
    ]
    assert in_post_reply_listen_window(recent, max_messages=3) is True


def test_build_session_flags_recent_dismissal():
    messages = [
        ContextMessage(id=1, role="assistant", content="ok"),
        ContextMessage(id=2, role="user", content="ванесса хватит"),
    ]
    state = build_chat_session_state(
        messages,
        max_idle_seconds=0,
        listen_max_messages=3,
    )
    assert state.has_recent_dismissal is True
    assert state.in_listen_window is False
    assert state.recent_messages == state.messages
