from vanessa.config.content import AppContent
from vanessa.config.owners import is_owner
from vanessa.config.settings import settings
from vanessa.core.messages import PhotoCandidate, WebResult
from vanessa.knowledge.users.nicknames import format_aliases_for_prompt
from vanessa.pipeline.llm.prompts.budget import (
    PRIORITY_DIRECTIVES,
    PRIORITY_SCENE,
    PRIORITY_WEB,
    BudgetPart,
    truncate_body,
)


def aliases_parts(content: AppContent) -> list[BudgetPart]:
    llm = content.llm
    aliases_text = format_aliases_for_prompt()
    if not aliases_text:
        return []
    body = f"{llm.aliases_header.strip()}\n{aliases_text}"
    return [(PRIORITY_DIRECTIVES, "aliases", body)]


def _format_web_line(llm: object, block: WebResult, snippet_cap: int) -> str:
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
        return f"[{block.published_date}] {line}"
    return line


def _clarification_parts(
    content: AppContent, clarification_hint: str
) -> list[BudgetPart]:
    instruction = content.llm.clarification_instruction.strip()
    if not instruction:
        return []
    if clarification_hint and clarification_hint.strip():
        instruction += f"\nWhat is unclear: {clarification_hint.strip()}"
    return [(PRIORITY_DIRECTIVES, "directives", instruction)]


def _tone_parts(content: AppContent, tone: str | None) -> list[BudgetPart]:
    note_template = content.llm.tone_note.strip()
    if not tone or not note_template:
        return []
    note = note_template.format(tone=tone)
    return [(PRIORITY_DIRECTIVES, "directives", note)]


def clarification_or_tone_parts(
    content: AppContent,
    *,
    needs_clarification: bool,
    clarification_hint: str,
    tone: str | None,
) -> list[BudgetPart]:
    if needs_clarification:
        return _clarification_parts(content, clarification_hint)
    return _tone_parts(content, tone)


def attitude_parts(attitude_note: str | None) -> list[BudgetPart]:
    if not attitude_note or not attitude_note.strip():
        return []
    return [(PRIORITY_DIRECTIVES, "directives", attitude_note.strip())]


def detail_parts(
    content: AppContent, detail: str, attitude_note: str | None
) -> list[BudgetPart]:
    llm = content.llm
    if not detail or detail == "normal":
        return []
    if attitude_note and attitude_note.strip():
        return []
    note = (
        llm.detail_note_detailed.strip()
        if detail == "detailed"
        else llm.detail_note_brief.strip()
    )
    if not note:
        return []
    return [(PRIORITY_DIRECTIVES, "directives", note)]


def vision_and_owner_parts(
    content: AppContent, sender_telegram_id: int | None, *, has_image: bool
) -> list[BudgetPart]:
    llm = content.llm
    parts: list[BudgetPart] = []
    vision_note = llm.vision_note.strip()
    if has_image and vision_note:
        parts.append((PRIORITY_DIRECTIVES, "directives", vision_note))
    owner_note = llm.owner_message_note.strip()
    if is_owner(sender_telegram_id) and owner_note:
        parts.append((PRIORITY_DIRECTIVES, "directives", owner_note))
    return parts


def web_parts(
    content: AppContent, web_blocks: list[WebResult] | None
) -> list[BudgetPart]:
    if not web_blocks:
        return []
    llm = content.llm
    snippet_cap = settings.web_search_snippet_max_chars
    web_lines = [_format_web_line(llm, block, snippet_cap) for block in web_blocks]
    parts: list[BudgetPart] = [
        (PRIORITY_WEB, "web_blocks", f"{llm.web_header}\n" + "\n".join(web_lines))
    ]
    instruction = llm.web_instruction.strip()
    if instruction:
        parts.append((PRIORITY_DIRECTIVES, "directives", instruction))
    return parts


def photo_empty_parts(
    content: AppContent,
    photo_candidates: list[PhotoCandidate] | None,
    *,
    photo_requested: bool,
) -> list[BudgetPart]:
    llm = content.llm
    if photo_candidates or not photo_requested:
        return []
    note = llm.photo_album_empty_note.strip()
    if not note:
        return []
    return [(PRIORITY_DIRECTIVES, "directives", note)]


_SCENE_DIRECTIVE = (
    "The <scene> block is what you see right now through your eyes. "
    "Treat it as current sight, not chat history. Do not invent people, "
    "objects, or text that are not in the block."
)


def scene_parts(scene_description: str | None) -> list[BudgetPart]:
    if not scene_description or not scene_description.strip():
        return []
    body = f"<scene>\n{scene_description.strip()}\n</scene>"
    return [
        (PRIORITY_SCENE, "scene", body),
        (PRIORITY_DIRECTIVES, "directives", _SCENE_DIRECTIVE),
    ]
