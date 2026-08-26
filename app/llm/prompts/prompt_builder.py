from app.config.content import AppContent, MemeDefContent, get_content
from app.config.settings import settings
from app.core.users.display_names import resolve_sender_display_name
from app.core.messages import ContextBlock, ContextMessage
from app.knowledge.schema import KnowledgeBlock
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
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        meme_blocks: list[MemeDefContent] | None = None,
        meme_menu: list[MemeDefContent] | None = None,
        metrics_block: str | None = None,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        critic_feedback: str | None = None,
        tone: str | None = None,
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
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
        if knowledge_blocks:
            block_lines = [
                llm.knowledge_block_line.format(
                    kind=block.kind,
                    title=block.title,
                    content=block.content,
                )
                for block in knowledge_blocks
            ]
            parts.append(f"{llm.knowledge_header}\n" + "\n".join(block_lines))
        if humor_quotes:
            quote_lines = [
                llm.humor_quote_line.format(quote=quote)
                for quote in humor_quotes
            ]
            parts.append(f"{llm.humor_quotes_header}\n" + "\n".join(quote_lines))
        if meme_blocks:
            meme_lines = [
                llm.meme_line.format(
                    name=meme.name,
                    meaning=meme.meaning,
                    usage=meme.usage or "по ситуации",
                )
                for meme in meme_blocks
            ]
            parts.append(f"{llm.meme_header}\n" + "\n".join(meme_lines))
        if meme_menu:
            menu_lines = [
                llm.meme_menu_line.format(
                    name=meme.name,
                    usage=meme.usage or "по ситуации",
                )
                for meme in meme_menu
            ]
            parts.append(f"{llm.meme_menu_header}\n" + "\n".join(menu_lines))
        if metrics_block and metrics_block.strip():
            header = (
                self._content.metrics.feedback_header.strip()
                or "My mood and relationship notes about the sender:"
            )
            parts.append(f"{header}\n{metrics_block.strip()}")
        session_text = format_session_messages(
            session_messages or [],
            self._content,
        )
        if session_text:
            parts.append(f"{llm.session_header}\n{session_text}")
        if reply_to_text:
            reply_sender = resolve_sender_display_name(
                reply_to_sender_telegram_id,
                reply_to_sender_name,
            )
            reply_line = llm.reply_message_line.format(
                sender=reply_sender,
                content=reply_to_text,
            )
            parts.append(f"{llm.reply_message_header}\n{reply_line}")
        current_line = self.format_current_message(
            user_message,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
        )
        parts.append(f"{llm.current_message_header}\n{current_line}")
        if tone and llm.tone_note.strip():
            parts.append(llm.tone_note.strip().format(tone=tone))
        if critic_feedback and critic_feedback.strip():
            fix_header = (
                llm.critic.fix_instruction_header.strip()
                or "Humor editor's note (you MUST address it in the new version of the reply):"
            )
            parts.append(f"{fix_header}\n{critic_feedback.strip()}")
        owner_id = settings.required_user_telegram_id
        owner_note = llm.owner_message_note.strip()
        if (
            owner_id
            and sender_telegram_id == owner_id
            and owner_note
        ):
            parts.append(owner_note)
        return "\n\n".join(parts)

    @property
    def system_prompt(self) -> str:
        persona = self._content.persona
        llm = self._content.llm
        sections = [
            ("Persona", persona.identity_text()),
            ("Voice", persona.voice_text()),
            ("Content rules", persona.rules_text()),
            ("Context handling", llm.task_text()),
            ("Answer formulation", llm.answer_text()),
            ("Reply language", llm.language_text()),
        ]
        parts = [
            f"## {title}\n{body}" for title, body in sections if body
        ]
        profanity = self._content.profanity
        if profanity.enabled and profanity.instruction.strip():
            parts.append(f"## Emotional language\n{profanity.instruction.strip()}")
        stickers = self._content.stickers
        if stickers.enabled and llm.sticker_instruction.strip():
            instruction = llm.sticker_instruction.strip()
            tag_lines = stickers.tag_lines()
            if tag_lines:
                instruction += (
                    "\n\nAvailable sticker tags (ONLY these exist in the pack — "
                    "use exactly these tags, nothing else):\n" + "\n".join(tag_lines)
                )
            parts.append(f"## Stickers\n{instruction}")
        return "\n\n".join(parts)
