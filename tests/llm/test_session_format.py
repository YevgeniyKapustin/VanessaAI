from datetime import datetime, timezone

from app.core.messages import ContextMessage
from app.llm.prompts.prompt_builder import PromptBuilder


def test_build_user_prompt_includes_session_context():
    builder = PromptBuilder()
    session = [
        ContextMessage(
            id=1,
            role="user",
            content="про тик ток",
            sender_name="Евгений",
            created_at=datetime(2026, 7, 4, 4, 8, tzinfo=timezone.utc),
        ),
        ContextMessage(
            id=2,
            role="assistant",
            content="поняла",
            created_at=datetime(2026, 7, 4, 4, 9, tzinfo=timezone.utc),
        ),
    ]
    prompt = builder.build_user_prompt("где там...", [], session_messages=session)

    assert "Recent correspondence" in prompt
    assert "про тик ток" in prompt
    assert "[assistant] поняла" in prompt
    assert prompt.index("Recent correspondence") < prompt.index("Current message")
    assert "где там..." in prompt


def test_session_renders_reply_marker_for_recent_message():
    builder = PromptBuilder()
    session = [
        ContextMessage(
            id=1,
            role="user",
            content="не делает карты",
            sender_name="Личь",
            created_at=datetime(2026, 7, 4, 4, 8, tzinfo=timezone.utc),
        ),
        ContextMessage(
            id=2,
            role="user",
            content="а я про то и говорю",
            sender_name="Евгений",
            created_at=datetime(2026, 7, 4, 4, 10, tzinfo=timezone.utc),
            reply_to_message_id=1,
            reply_to_text="не делает карты",
            reply_to_sender_telegram_id=99,
            reply_to_sender_name="Личь",
        ),
    ]
    prompt = builder.build_user_prompt("дальше что", [], session_messages=session)

    assert "Recent correspondence" in prompt
    assert "↳ reply to [Личь]: не делает карты" in prompt
    # the marker is attached right under the replying user line
    assert prompt.index("Евгений: а я про то и говорю") < prompt.index(
        "↳ reply to [Личь]"
    )
