from datetime import datetime, timezone

from app.core.messages import ContextMessage
from app.llm.prompt_builder import PromptBuilder


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

    assert "Недавняя переписка" in prompt
    assert "про тик ток" in prompt
    assert "[assistant] поняла" in prompt
    assert prompt.index("Недавняя переписка") < prompt.index("Текущее сообщение")
    assert "где там..." in prompt
