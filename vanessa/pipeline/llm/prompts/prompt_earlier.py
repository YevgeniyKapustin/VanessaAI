"""Compose block for the messages before the session idle gap.

The session window stops at the first long pause, so a turn after a pause
loses what was said before it, even the bot's own promise. This block shows
the tail of that older thread apart from the recent correspondence.
"""

from vanessa.config.content import AppContent
from vanessa.core.messages import ContextMessage
from vanessa.pipeline.llm.prompts.budget import PRIORITY_CONTEXT, BudgetPart
from vanessa.pipeline.llm.prompts.session_format import format_session_messages


def earlier_parts(
    content: AppContent, earlier_messages: list[ContextMessage] | None
) -> list[BudgetPart]:
    text = format_session_messages(earlier_messages or [], content)
    if not text:
        return []
    body = f"{content.llm.earlier_header}\n{text}"
    return [(PRIORITY_CONTEXT, "session_messages", body)]
