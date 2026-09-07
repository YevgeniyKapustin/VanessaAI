from datetime import datetime
from typing import Any

from vanessa.config.content import AppContent, get_content
from vanessa.config.settings import settings
from vanessa.core.generate_request import GenerateRequest, as_generate_request
from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    ImageAttachment,
)
from vanessa.pipeline.llm.photo_request import is_photo_request
from vanessa.pipeline.llm.prompts import (
    prompt_context,
    prompt_directives,
    prompt_format,
)
from vanessa.pipeline.llm.prompts.budget import PRIORITY_DIRECTIVES, apply_budget
from vanessa.pipeline.llm.prompts.prompt_system import build_system_prompt


def _photos_on(request: GenerateRequest) -> bool:
    profile = request.channel_profile
    return profile is None or profile.photos


def _stickers_on(request: GenerateRequest) -> bool:
    profile = request.channel_profile
    return profile is None or profile.stickers


def _photo_empty_parts(
    content: AppContent, request: GenerateRequest, *, photo_requested: bool
):
    if not _photos_on(request):
        return []
    return prompt_directives.photo_empty_parts(
        content,
        request.photo_candidates,
        photo_requested=photo_requested,
    )


def _meme_parts(content: AppContent, request: GenerateRequest):
    if not _stickers_on(request):
        return []
    return prompt_context.meme_parts(
        content, request.meme_blocks, request.meme_menu
    )


def _photo_album_parts(
    content: AppContent, request: GenerateRequest, *, photo_requested: bool
):
    if not _photos_on(request):
        return []
    return prompt_context.photo_album_parts(
        content,
        request.photo_candidates,
        photo_requested=photo_requested,
    )


def _final_task_parts(content: AppContent):
    final_task = content.llm.final_task_text()
    if not final_task:
        return []
    return [(PRIORITY_DIRECTIVES, "final_task", final_task)]


class PromptBuilder:
    """Assemble the compose prompt following the recommended block order:

    system message (blocks 1-3): role/persona -> constraints/rules -> examples;
    user prompt (blocks 4-5):     input data -> final task.
    """

    def __init__(self, content: AppContent | None = None) -> None:
        self._content = content or get_content()

    def format_message_line(self, message: ContextMessage) -> str:
        return prompt_format.format_message_line(message)

    def format_context_block(self, index: int, block: ContextBlock) -> str:
        return prompt_format.format_context_block(self._content, index, block)

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
        return prompt_format.format_current_message(
            content,
            sender_telegram_id=sender_telegram_id,
            sender_name=sender_name,
            created_at=created_at,
            reply_to_text=reply_to_text,
            images=images,
        )

    def build_user_prompt(
        self,
        user_message: str | GenerateRequest,
        context_blocks: list[ContextBlock] | None = None,
        **kwargs: Any,
    ) -> str:
        request = as_generate_request(user_message, context_blocks, **kwargs)
        photo_requested = is_photo_request(request.user_message)
        content = self._content
        parts = []
        parts.extend(prompt_directives.aliases_parts(content))
        parts.extend(
            prompt_directives.clarification_or_tone_parts(
                content,
                needs_clarification=request.needs_clarification,
                clarification_hint=request.clarification_hint,
                tone=request.tone,
            )
        )
        parts.extend(prompt_directives.attitude_parts(request.attitude_note))
        parts.extend(
            prompt_directives.detail_parts(
                content, request.detail, request.attitude_note
            )
        )
        parts.extend(
            prompt_directives.vision_and_owner_parts(
                content,
                request.sender_telegram_id,
                has_image=bool(request.images),
            )
        )
        parts.extend(
            _photo_empty_parts(
                content, request, photo_requested=photo_requested
            )
        )
        parts.extend(
            prompt_context.history_parts(
                content, request.context_blocks, self.format_context_block
            )
        )
        parts.extend(prompt_context.knowledge_parts(content, request.knowledge_blocks))
        parts.extend(prompt_directives.scene_parts(request.scene_description))
        parts.extend(prompt_directives.web_parts(content, request.web_blocks))
        parts.extend(prompt_context.humor_parts(content, request.humor_quotes))
        parts.extend(_meme_parts(content, request))
        parts.extend(prompt_context.metrics_parts(content, request.metrics_block))
        parts.extend(prompt_context.session_parts(content, request.session_messages))
        parts.extend(
            _photo_album_parts(
                content, request, photo_requested=photo_requested
            )
        )
        parts.extend(
            prompt_context.current_message_parts(
                content,
                request.user_message,
                sender_telegram_id=request.sender_telegram_id,
                sender_name=request.sender_name,
                reply_to_text=request.reply_to_text,
                current_images=request.current_images,
                format_current_message=prompt_format.format_current_message,
            )
        )
        parts.extend(_final_task_parts(content))
        budget = content.llm.budget
        enabled = bool(settings.compose_budget_enabled and budget.enabled)
        parts = apply_budget(parts, budget, enabled=enabled)
        return "\n\n".join(body for _, _, body in parts)

    @property
    def system_prompt(self) -> str:
        return build_system_prompt(self._content)
