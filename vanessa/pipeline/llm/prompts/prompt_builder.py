from datetime import UTC, datetime

from vanessa.config.content import AppContent, MemeDefContent, get_content
from vanessa.config.settings import settings
from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    ImageAttachment,
    PhotoCandidate,
    WebResult,
)
from vanessa.knowledge.schema import KnowledgeBlock
from vanessa.knowledge.users.display_names import resolve_sender_display_name
from vanessa.knowledge.users.nicknames import format_aliases_for_prompt
from vanessa.pipeline.llm.photo_request import is_photo_request
from vanessa.pipeline.llm.prompts.budget import (
    PRIORITY_CONTEXT,
    PRIORITY_CURRENT,
    PRIORITY_DIRECTIVES,
    PRIORITY_HUMOR,
    PRIORITY_KNOWLEDGE,
    PRIORITY_MEME,
    PRIORITY_MEME_MENU,
    PRIORITY_METRICS,
    PRIORITY_SESSION,
    PRIORITY_WEB,
    apply_budget,
    truncate_body,
)
from vanessa.pipeline.llm.prompts.context_format import block_time_range, format_message_time
from vanessa.pipeline.llm.prompts.message_xml import (
    BOT_SENDER,
    message_attachment_blocks,
    render_messages,
    render_msg,
    xml_attr,
    xml_text,
)
from vanessa.pipeline.llm.prompts.session_format import format_session_messages


class PromptBuilder:
    """Assemble the compose prompt following the recommended block order:

    system message (blocks 1-3): role/persona -> constraints/rules -> examples;
    user prompt (blocks 4-5):     input data -> final task.
    """

    def __init__(self, content: AppContent | None = None) -> None:
        self._content = content or get_content()

    def format_message_line(self, message: ContextMessage) -> str:
        time_label = format_message_time(message.created_at)
        if message.role == "assistant":
            sender = BOT_SENDER
        else:
            sender = resolve_sender_display_name(
                message.sender_telegram_id,
                message.sender_name,
            )
        # One <msg> element (XML input-block convention): a verbatim <text>,
        # plus <reply_text> / <attachment> children and metadata attributes.
        return render_msg(
            content=message.content,
            sender=sender,
            time=time_label,
            msg_id=message.id,
            anchor=message.is_anchor,
            reply_to=message.reply_to_message_id,
            reply_text=message.reply_to_text,
            attachments=message_attachment_blocks(
                message.attachments,
                message.photo_caption,
            ),
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
        return "\n".join([header, render_messages(lines)])

    def format_current_message(
        self,
        content: str,
        *,
        sender_telegram_id: int | None = None,
        sender_name: str | None = None,
        created_at: datetime | None = None,
        reply_to_text: str | None = None,
        images: list[ImageAttachment] | None = None,
    ) -> str:
        """Render the current message as a ``<msg>`` element.

        ``images`` are the photos attached to THIS message (the current turn's
        own images). They are rendered as ``<attachment>`` children in the SAME
        ``<msg>`` as the ``<text>`` — the same convention as the session and
        context blocks — so the model always sees a photo right next to its
        caption instead of a detached album entry. Every attached photo is
        rendered (a message that carried several keeps them all together).
        """
        sender = resolve_sender_display_name(sender_telegram_id, sender_name)
        time_label = format_message_time(created_at or datetime.now(UTC))
        msg = render_msg(
            content=content,
            sender=sender,
            time=time_label,
            reply_text=reply_to_text,
            attachments=message_attachment_blocks(images) if images else None,
        )
        return render_messages([msg])

    def build_user_prompt(
        self,
        user_message: str,
        context_blocks: list[ContextBlock],
        session_messages: list[ContextMessage] | None = None,
        humor_quotes: list[str] | None = None,
        knowledge_blocks: list[KnowledgeBlock] | None = None,
        web_blocks: list[WebResult] | None = None,
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
        detail: str = "normal",
        reply_to_text: str | None = None,
        reply_to_sender_telegram_id: int | None = None,
        reply_to_sender_name: str | None = None,
        has_image: bool = False,
        photo_candidates: list[PhotoCandidate] | None = None,
        current_images: list[ImageAttachment] | None = None,
    ) -> str:
        llm = self._content.llm
        # Recommended block order for the user prompt (blocks 4-5):
        #   constraints/directives (upper middle) -> input data (closer to the
        #   end) -> final task (very end, the freshest model memory).
        #
        # Budgeted parts: (priority, section, body). Section names match the
        # PromptBudgetContent fields so per-section caps apply generically; the
        # priority controls which sections survive the global cap.
        parts: list[tuple[int, str, str]] = []

        # --- Constraints / directives (upper middle) -------------------------
        # Short turn-level rules that apply regardless of the input; they come
        # before all dynamic data so the model reads them as standing rules.
        aliases_text = format_aliases_for_prompt()
        if aliases_text:
            parts.append(
                (PRIORITY_DIRECTIVES, "aliases", f"{llm.aliases_header.strip()}\n{aliases_text}")
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
        # Detail-level directive: the planner/heuristic decided the reply should
        # be brief or detailed. Skipped when the cold/annoyance note is present —
        # an annoyed Vanessa stays brief regardless of the user's request.
        if (
            detail
            and detail != "normal"
            and not (attitude_note and attitude_note.strip())
        ):
            note = (
                llm.detail_note_detailed.strip()
                if detail == "detailed"
                else llm.detail_note_brief.strip()
            )
            if note:
                parts.append((PRIORITY_DIRECTIVES, "directives", note))
        if has_image and llm.vision_note.strip():
            # Vision directive: the turn carries an image — describe / OCR it and
            # be honest about unclear text instead of hallucinating.
            parts.append((PRIORITY_DIRECTIVES, "directives", llm.vision_note.strip()))
        owner_id = settings.required_user_telegram_id
        owner_note = llm.owner_message_note.strip()
        if (
            owner_id
            and sender_telegram_id == owner_id
            and owner_note
        ):
            parts.append((PRIORITY_DIRECTIVES, "directives", owner_note))
        photo_requested = is_photo_request(user_message)
        if (
            not photo_candidates
            and photo_requested
            and llm.photo_album_empty_note.strip()
        ):
            # No photos available and the user asked for one: force an honest
            # refusal instead of letting the model fake a "sent" claim. Rendered
            # only on an explicit photo request to avoid noise on every turn.
            parts.append(
                (PRIORITY_DIRECTIVES, "directives", llm.photo_album_empty_note.strip())
            )

        # --- Input data (closer to the end) ----------------------------------
        if context_blocks:
            separator = llm.context_block_separator.strip() or "\n\n"
            blocks_text = separator.join(
                self.format_context_block(index, block)
                for index, block in enumerate(context_blocks, start=1)
            )
            history_block = f"{llm.context_header}\n{blocks_text}"
        else:
            history_block = llm.context_header
        parts.append((PRIORITY_CONTEXT, "context_blocks", history_block))
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
        # Live web search results (the "googling" skill): rendered as their own
        # block when the planner flagged the turn for web search and the Retrieve
        # stage found results. Each snippet is cut at a boundary to the settings
        # cap; the whole block is then handled by the prompt budget (web_blocks).
        if web_blocks:
            snippet_cap = settings.web_search_snippet_max_chars
            web_lines: list[str] = []
            for block in web_blocks:
                snippet = block.snippet or ""
                if snippet_cap > 0:
                    snippet = truncate_body(snippet, snippet_cap)
                title = block.title or block.url
                line = llm.web_block_line.format(
                    title=title,
                    url=block.url,
                    snippet=snippet,
                )
                if block.published_date:
                    # Freshness marker at the line start (e.g. [2026-08-28]),
                    # so the model can judge how current the source is.
                    line = f"[{block.published_date}] {line}"
                web_lines.append(line)
            parts.append(
                (PRIORITY_WEB, "web_blocks", f"{llm.web_header}\n" + "\n".join(web_lines))
            )
            if llm.web_instruction.strip():
                parts.append(
                    (PRIORITY_DIRECTIVES, "directives", llm.web_instruction.strip())
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
        if photo_candidates:
            # Photo album: photos the bot could re-send, matched to the context
            # by RAG "по смыслу" + the recent session. Kept as ONE coupled block
            # (list + its usage instructions) right before the current message:
            # the instructions reference "the photos listed above", so splitting
            # them from the list would break the reference. Rendered as
            # <attachment> entries inside an <attachments> root (XML input-block
            # convention); the values are escaped so a literal <...> / & never
            # breaks the markup.
            album_lines = [
                llm.photo_album_line.format(
                    index=candidate.index,
                    sender=xml_attr(candidate.sender_name or "кто-то"),
                    time=xml_attr(format_message_time(candidate.created_at)),
                    caption=xml_text(candidate.caption),
                )
                for candidate in photo_candidates
            ]
            album = (
                f"{llm.photo_album_header}\n"
                "<attachments>\n"
                + "\n".join(album_lines)
                + "\n</attachments>"
            )
            parts.append((PRIORITY_DIRECTIVES, "photo_album", album))
            if llm.photo_album_instruction.strip():
                parts.append(
                    (PRIORITY_DIRECTIVES, "directives", llm.photo_album_instruction.strip())
                )
            if photo_requested and llm.photo_request_required_note.strip():
                # The user explicitly asked for a photo: the marker is mandatory,
                # not optional — the model must not "say" it sent one.
                parts.append(
                    (PRIORITY_DIRECTIVES, "directives", llm.photo_request_required_note.strip())
                )
        # The current message is the one to reply to. A reply-to quote is folded
        # into the same <msg> as <reply_text> (XML input-block convention) rather
        # than rendered as a separate section.
        current_line = self.format_current_message(
            user_message,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
            reply_to_text=reply_to_text,
            images=current_images,
        )
        current_header = llm.current_message_header
        if reply_to_text and llm.reply_message_header.strip():
            current_header = f"{llm.reply_message_header.strip()}\n{current_header}"
        parts.append(
            (PRIORITY_CURRENT, "current_message", f"{current_header}\n{current_line}")
        )

        # --- Final task (very end) -------------------------------------------
        # A short, explicit call to action in the freshest part of the model's
        # memory, right after the current message.
        final_task = llm.final_task_text()
        if final_task:
            parts.append((PRIORITY_DIRECTIVES, "final_task", final_task))

        # Enforce the compose-prompt budget: per-section caps + a global cap
        # (trimming lowest-priority sections first). Never cuts the current
        # message or the short directives (including the final task).
        budget = self._content.llm.budget
        enabled = bool(settings.compose_budget_enabled and budget.enabled)
        parts = apply_budget(parts, budget, enabled=enabled)

        return "\n\n".join(body for _, _, body in parts)

    @property
    def system_prompt(self) -> str:
        # Recommended block order for the system message (blocks 1-3):
        #   role/persona -> constraints/rules -> few-shot examples.
        # The examples close the system message so they sit right before the
        # dynamic input data that opens the user prompt (block 4) and the final
        # task that closes it (block 5).
        persona = self._content.persona
        llm = self._content.llm
        sections = [
            ("Persona", persona.identity_text()),
            ("Voice", persona.voice_text()),
            ("Content rules", persona.rules_text()),
            ("Context handling", llm.task_text()),
            ("Answer formulation", llm.answer_format_text()),
            ("Reply language", llm.language_text()),
        ]
        parts = [
            f"## {title}\n{body}" for title, body in sections if body
        ]
        profanity = self._content.profanity
        if profanity.enabled and profanity.instruction.strip():
            parts.append(f"## Emotional language\n{profanity.instruction.strip()}")
        stickers = self._content.stickers
        if stickers.enabled:
            sections: list[str] = []
            instruction = llm.sticker_instruction.strip()
            if instruction:
                sections.append(instruction)
            xml_block = stickers.xml_system_block()
            if xml_block:
                sections.append(xml_block)
            if sections:
                parts.append("## Stickers\n" + "\n\n".join(sections))
        # Few-shot examples — their own block, after every constraint (the
        # recommended "lower middle" position). The yaml block already carries
        # its own "## Examples" header, so it is appended whole.
        examples = llm.examples_text()
        if examples:
            parts.append(examples)
        return "\n\n".join(parts)
