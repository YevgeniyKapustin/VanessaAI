from datetime import datetime

from app.config.content import AppContent, MemeDefContent, get_content
from app.config.settings import settings
from app.core.users.display_names import resolve_sender_display_name
from app.core.users.nicknames import format_aliases_for_prompt
from app.core.messages import ContextBlock, ContextMessage, PhotoCandidate
from app.knowledge.schema import KnowledgeBlock
from app.llm.prompts.budget import (
    PRIORITY_CONTEXT,
    PRIORITY_CURRENT,
    PRIORITY_DIRECTIVES,
    PRIORITY_HUMOR,
    PRIORITY_KNOWLEDGE,
    PRIORITY_MEME,
    PRIORITY_MEME_MENU,
    PRIORITY_METRICS,
    PRIORITY_REPLY,
    PRIORITY_SESSION,
    apply_budget,
)
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
        created_at: datetime | None = None,
    ) -> str:
        llm = self._content.llm
        sender = resolve_sender_display_name(sender_telegram_id, sender_name)
        time_label = format_message_time(created_at or datetime.now())
        return llm.current_message_line.format(
            time=time_label,
            sender=sender,
            content=content,
        )

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
        attitude_note: str | None = None,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        tone: str | None = None,
        needs_clarification: bool = False,
        clarification_hint: str = "",
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        has_image: bool = False,
        photo_candidates: list[PhotoCandidate] | None = None,
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

        # Budgeted parts: (priority, section, body). Section names match the
        # PromptBudgetContent fields so per-section caps apply generically; the
        # priority controls which sections survive the global cap.
        parts = [(PRIORITY_CONTEXT, "context_blocks", history_block)]
        if knowledge_blocks:
            block_lines = [
                llm.knowledge_block_line.format(
                    kind=block.kind,
                    title=block.title,
                    content=block.content,
                )
                for block in knowledge_blocks
            ]
            parts.append(
                (PRIORITY_KNOWLEDGE, "knowledge_blocks", f"{llm.knowledge_header}\n" + "\n".join(block_lines))
            )
        if humor_quotes:
            quote_lines = [
                llm.humor_quote_line.format(quote=quote)
                for quote in humor_quotes
            ]
            parts.append(
                (PRIORITY_HUMOR, "humor_quotes", f"{llm.humor_quotes_header}\n" + "\n".join(quote_lines))
            )
        if meme_blocks:
            meme_lines = [
                llm.meme_line.format(
                    name=meme.name,
                    meaning=meme.meaning,
                    usage=meme.usage or "по ситуации",
                )
                for meme in meme_blocks
            ]
            parts.append(
                (PRIORITY_MEME, "meme_blocks", f"{llm.meme_header}\n" + "\n".join(meme_lines))
            )
        if meme_menu:
            menu_lines = [
                llm.meme_menu_line.format(
                    name=meme.name,
                    usage=meme.usage or "по ситуации",
                )
                for meme in meme_menu
            ]
            parts.append(
                (PRIORITY_MEME_MENU, "meme_menu", f"{llm.meme_menu_header}\n" + "\n".join(menu_lines))
            )
        if metrics_block and metrics_block.strip():
            header = (
                self._content.metrics.feedback_header.strip()
                or "My mood and relationship notes about the sender:"
            )
            parts.append(
                (PRIORITY_METRICS, "metrics_block", f"{header}\n{metrics_block.strip()}")
            )
        session_text = format_session_messages(
            session_messages or [],
            self._content,
        )
        if session_text:
            parts.append(
                (PRIORITY_SESSION, "session_messages", f"{llm.session_header}\n{session_text}")
            )
        aliases_text = format_aliases_for_prompt()
        if aliases_text:
            parts.append(
                (PRIORITY_DIRECTIVES, "aliases", f"{llm.aliases_header.strip()}\n{aliases_text}")
            )
        if reply_to_text:
            reply_sender = resolve_sender_display_name(
                reply_to_sender_telegram_id,
                reply_to_sender_name,
            )
            reply_line = llm.reply_message_line.format(
                sender=reply_sender,
                content=reply_to_text,
            )
            parts.append(
                (PRIORITY_REPLY, "reply_to", f"{llm.reply_message_header}\n{reply_line}")
            )
        current_line = self.format_current_message(
            user_message,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
        )
        parts.append(
            (PRIORITY_CURRENT, "current_message", f"{llm.current_message_header}\n{current_line}")
        )
        if needs_clarification and llm.clarification_instruction.strip():
            instruction = llm.clarification_instruction.strip()
            if clarification_hint and clarification_hint.strip():
                instruction += f"\nWhat is unclear: {clarification_hint.strip()}"
            parts.append((PRIORITY_DIRECTIVES, "directives", instruction))
        elif tone and llm.tone_note.strip():
            parts.append(
                (PRIORITY_DIRECTIVES, "directives", llm.tone_note.strip().format(tone=tone))
            )
        if attitude_note and attitude_note.strip():
            # Cold-reply directive: the sender is stuck in a same-topic loop and
            # Vanessa is annoyed — reply dry, sharp and brief.
            parts.append((PRIORITY_DIRECTIVES, "directives", attitude_note.strip()))
        if has_image and llm.vision_note.strip():
            # Vision directive: the turn carries an image — describe / OCR it and
            # be honest about unclear text instead of hallucinating.
            parts.append((PRIORITY_DIRECTIVES, "directives", llm.vision_note.strip()))
        if photo_candidates:
            # Photo album: photos the bot could re-send, matched to the context
            # by RAG "по смыслу" + the recent session. High priority so the model
            # can always choose to send one.
            album_lines = [
                llm.photo_album_line.format(
                    index=candidate.index,
                    sender=candidate.sender_name or "кто-то",
                    time=format_message_time(candidate.created_at),
                    caption=candidate.caption,
                )
                for candidate in photo_candidates
            ]
            parts.append(
                (
                    PRIORITY_DIRECTIVES,
                    "photo_album",
                    f"{llm.photo_album_header}\n" + "\n".join(album_lines),
                )
            )
            if llm.photo_album_instruction.strip():
                parts.append(
                    (PRIORITY_DIRECTIVES, "directives", llm.photo_album_instruction.strip())
                )
        owner_id = settings.required_user_telegram_id
        owner_note = llm.owner_message_note.strip()
        if (
            owner_id
            and sender_telegram_id == owner_id
            and owner_note
        ):
            parts.append((PRIORITY_DIRECTIVES, "directives", owner_note))

        # Enforce the compose-prompt budget: per-section caps + a global cap
        # (trimming lowest-priority sections first). Never cuts the current
        # message or the short directives.
        budget = self._content.llm.budget
        enabled = bool(settings.compose_budget_enabled and budget.enabled)
        parts = apply_budget(parts, budget, enabled=enabled)

        return "\n\n".join(body for _, _, body in parts)

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
