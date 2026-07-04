from app.config.content import AppContent, get_content
from app.core.users.display_names import resolve_sender_display_name
from app.core.messages import ContextBlock, ContextMessage
from app.llm.prompts.context_format import block_time_range, format_message_time
from app.llm.prompts.session_format import format_session_messages


class PromptBuilder:
    def __init__(self, content: AppContent | None = None) -> None:
        self._content = content or get_content()

    def format_message_line(self, message: ContextMessage) -> str:
        llm = self._content.llm
        time_label = format_message_time(message.created_at)
        anchor = llm.anchor_marker if message.is_anchor else ""
        if message.role == "assistant":
            return llm.assistant_line.format(
                time=time_label,
                anchor=anchor,
                content=message.content,
            )
        sender = resolve_sender_display_name(
            message.sender_telegram_id,
            message.sender_name,
        )
        return llm.user_line.format(
            time=time_label,
            sender=sender,
            anchor=anchor,
            content=message.content,
        )

    def format_context_block(self, index: int, block: ContextBlock) -> str:
        llm = self._content.llm
        started_at, ended_at = block_time_range(block.messages)
        header = llm.context_block_header.format(
            index=index,
            started_at=started_at,
            ended_at=ended_at,
        )
        lines = [self.format_message_line(message) for message in block.messages]
        return "\n".join([header, *lines])

    def format_current_message(
        self,
        content: str,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
    ) -> str:
        llm = self._content.llm
        sender = resolve_sender_display_name(sender_telegram_id, sender_name)
        return llm.current_message_line.format(sender=sender, content=content)

    def build_user_prompt(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
    ) -> str:
        llm = self._content.llm
        if context_blocks:
            separator = llm.context_block_separator.strip() or "\n\n"
            blocks_text = separator.join(
                self.format_context_block(index, block)
                for index, block in enumerate(context_blocks, start=1)
            )
            history_block = f"{llm.context_header}\n{blocks_text}"
        else:
            history_block = llm.context_header

        parts = [history_block]
        if humor_quotes:
            quote_lines = [
                llm.humor_quote_line.format(quote=quote)
                for quote in humor_quotes
            ]
            parts.append(f"{llm.humor_quotes_header}\n" + "\n".join(quote_lines))
        session_text = format_session_messages(
            session_messages or [],
            self._content,
        )
        if session_text:
            parts.append(f"{llm.session_header}\n{session_text}")
        current_line = self.format_current_message(
            user_message,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
        )
        parts.append(f"{llm.current_message_header}\n{current_line}")
        return "\n\n".join(parts)

    @property
    def system_prompt(self) -> str:
        persona = self._content.persona
        llm = self._content.llm
        sections = [
            ("Личность", persona.identity_text()),
            ("Голос", persona.voice_text()),
            ("Правила контента", persona.rules_text()),
            ("Работа с контекстом", llm.task_text()),
            ("Формулировка ответа", llm.answer_text()),
        ]
        parts = [
            f"## {title}\n{body}" for title, body in sections if body
        ]
        profanity = self._content.profanity
        if profanity.enabled and profanity.instruction.strip():
            parts.append(f"## Эмоциональная лексика\n{profanity.instruction.strip()}")
        return "\n\n".join(parts)
