from collections.abc import Callable

from vanessa.config.content import AppContent, MemeDefContent
from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    ImageAttachment,
    PhotoCandidate,
)
from vanessa.knowledge.schema import KnowledgeBlock
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
    BudgetPart,
)
from vanessa.pipeline.llm.prompts.context_format import format_message_time
from vanessa.pipeline.llm.prompts.message_xml import xml_attr, xml_text
from vanessa.pipeline.llm.prompts.session_format import format_session_messages


def history_parts(
    content: AppContent,
    context_blocks: list[ContextBlock],
    format_context_block: Callable[[int, ContextBlock], str],
) -> list[BudgetPart]:
    llm = content.llm
    if not context_blocks:
        return [(PRIORITY_CONTEXT, "context_blocks", llm.context_header)]
    separator = llm.context_block_separator.strip() or "\n\n"
    blocks_text = separator.join(
        format_context_block(index, block)
        for index, block in enumerate(context_blocks, start=1)
    )
    history_block = f"{llm.context_header}\n{blocks_text}"
    return [(PRIORITY_CONTEXT, "context_blocks", history_block)]


def knowledge_parts(
    content: AppContent, knowledge_blocks: list[KnowledgeBlock] | None
) -> list[BudgetPart]:
    if not knowledge_blocks:
        return []
    llm = content.llm
    block_lines = [
        llm.knowledge_block_line.format(
            kind=block.kind,
            title=block.title,
            content=block.content,
        )
        for block in knowledge_blocks
    ]
    body = f"{llm.knowledge_header}\n" + "\n".join(block_lines)
    return [(PRIORITY_KNOWLEDGE, "knowledge_blocks", body)]


def humor_parts(
    content: AppContent, humor_quotes: list[str] | None
) -> list[BudgetPart]:
    if not humor_quotes:
        return []
    llm = content.llm
    quote_lines = [
        llm.humor_quote_line.format(quote=quote) for quote in humor_quotes
    ]
    body = f"{llm.humor_quotes_header}\n" + "\n".join(quote_lines)
    return [(PRIORITY_HUMOR, "humor_quotes", body)]


def meme_parts(
    content: AppContent,
    meme_blocks: list[MemeDefContent] | None,
    meme_menu: list[MemeDefContent] | None,
) -> list[BudgetPart]:
    llm = content.llm
    parts: list[BudgetPart] = []
    if meme_blocks:
        meme_lines = [
            llm.meme_line.format(
                name=meme.name,
                meaning=meme.meaning,
                usage=meme.usage or "по ситуации",
            )
            for meme in meme_blocks
        ]
        body = f"{llm.meme_header}\n" + "\n".join(meme_lines)
        parts.append((PRIORITY_MEME, "meme_blocks", body))
    if meme_menu:
        menu_lines = [
            llm.meme_menu_line.format(
                name=meme.name,
                usage=meme.usage or "по ситуации",
            )
            for meme in meme_menu
        ]
        body = f"{llm.meme_menu_header}\n" + "\n".join(menu_lines)
        parts.append((PRIORITY_MEME_MENU, "meme_menu", body))
    return parts


def metrics_parts(
    content: AppContent, metrics_block: str | None
) -> list[BudgetPart]:
    if not metrics_block or not metrics_block.strip():
        return []
    header = (
        content.metrics.feedback_header.strip()
        or "My mood and relationship notes about the sender:"
    )
    body = f"{header}\n{metrics_block.strip()}"
    return [(PRIORITY_METRICS, "metrics_block", body)]


def session_parts(
    content: AppContent, session_messages: list[ContextMessage] | None
) -> list[BudgetPart]:
    session_text = format_session_messages(
        session_messages or [],
        content,
    )
    if not session_text:
        return []
    llm = content.llm
    body = f"{llm.session_header}\n{session_text}"
    return [(PRIORITY_SESSION, "session_messages", body)]


def photo_album_parts(
    content: AppContent,
    photo_candidates: list[PhotoCandidate] | None,
    *,
    photo_requested: bool,
) -> list[BudgetPart]:
    if not photo_candidates:
        return []
    llm = content.llm
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
    parts: list[BudgetPart] = [(PRIORITY_DIRECTIVES, "photo_album", album)]
    instruction = llm.photo_album_instruction.strip()
    if instruction:
        parts.append((PRIORITY_DIRECTIVES, "directives", instruction))
    required = llm.photo_request_required_note.strip()
    if photo_requested and required:
        parts.append((PRIORITY_DIRECTIVES, "directives", required))
    return parts


def current_message_parts(
    content: AppContent,
    user_message: str,
    *,
    sender_telegram_id: int | None,
    sender_name: str | None,
    reply_to_text: str | None,
    current_images: list[ImageAttachment] | None,
    format_current_message: Callable[..., str],
) -> list[BudgetPart]:
    llm = content.llm
    current_line = format_current_message(
        user_message,
        sender_telegram_id=sender_telegram_id,
        sender_name=sender_name,
        reply_to_text=reply_to_text,
        images=current_images,
    )
    current_header = llm.current_message_header
    if reply_to_text and llm.reply_message_header.strip():
        current_header = f"{llm.reply_message_header.strip()}\n{current_header}"
    body = f"{current_header}\n{current_line}"
    return [(PRIORITY_CURRENT, "current_message", body)]
