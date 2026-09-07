from vanessa.core.messages import ContextMessage
from vanessa.knowledge.memory.memory_prefilter import (
    memory_potential_score,
    should_extract_memory,
)
from vanessa.knowledge.memory.memory_transcript import format_memory_transcript


def _msg(
    content: str,
    *,
    role: str = "user",
    sender_id: int | None = 1,
    sender_name: str | None = "Ada",
    msg_id: int = 1,
) -> ContextMessage:
    return ContextMessage(
        id=msg_id,
        role=role,
        content=content,
        sender_telegram_id=sender_id,
        sender_name=sender_name,
    )


def test_prefilter_empty_and_short() -> None:
    assert should_extract_memory([]) is False
    assert should_extract_memory([_msg("ok")]) is False
    assert should_extract_memory([_msg("   ")], min_messages=1) is False


def test_prefilter_quote_disclosure_and_url() -> None:
    messages = [
        _msg("«я переезжаю на новую работу https://example.com 2024» " + "x" * 40),
        _msg("поняла, спасибо большое за подробности про переезд", role="assistant"),
    ]
    assert should_extract_memory(messages) is True
    score, breakdown = memory_potential_score(messages)
    assert score > 0
    assert breakdown["has_quote"] or breakdown["has_specifics"]


def test_prefilter_long_message_bonus() -> None:
    long_text = "факт про работу и семью " * 20
    score, breakdown = memory_potential_score([_msg(long_text)])
    long_min = 200
    assert breakdown["max_user_len"] >= long_min
    assert score >= 1.0


def test_transcript_labels_users_and_skips_blank() -> None:
    text = format_memory_transcript(
        [
            _msg("   "),
            _msg("hello", sender_id=None, sender_name="Ada"),
            _msg("hi", sender_id=None, sender_name=None),
            _msg("pong", role="assistant", sender_id=None),
            _msg("id only", sender_id=99, sender_name=None),
        ]
    )
    assert "[assistant]" in text
    assert "hello" in text
    assert "id only" in text
    assert "   " not in text
