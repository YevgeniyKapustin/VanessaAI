from dataclasses import dataclass, fields
from typing import Any

from vanessa.config.channels import ChannelProfile
from vanessa.config.content import MemeDefContent
from vanessa.core.knowledge_dto import KnowledgeBlock
from vanessa.core.messages import (
    ContextBlock,
    ContextMessage,
    ImageAttachment,
    PhotoCandidate,
    WebResult,
)


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    """Compose-turn payload shared by providers, prompt builder, and prompt logs."""

    user_message: str
    context_blocks: list[ContextBlock]
    session_messages: list[ContextMessage] | None = None
    humor_quotes: list[str] | None = None
    knowledge_blocks: list[KnowledgeBlock] | None = None
    web_blocks: list[WebResult] | None = None
    meme_blocks: list[MemeDefContent] | None = None
    meme_menu: list[MemeDefContent] | None = None
    metrics_block: str | None = None
    attitude_note: str | None = None
    sender_telegram_id: int | None = None
    sender_name: str | None = None
    system_prompt: str | None = None
    tone: str | None = None
    needs_clarification: bool = False
    clarification_hint: str = ""
    detail: str = "normal"
    reply_to_text: str | None = None
    reply_to_sender_telegram_id: int | None = None
    reply_to_sender_name: str | None = None
    images: list[ImageAttachment] | None = None
    photo_candidates: list[PhotoCandidate] | None = None
    current_images: list[ImageAttachment] | None = None
    scene_description: str | None = None
    # Hermes ask outcome: "asked" | "offline" | None (see prompt_hermes).
    hermes_status: str | None = None
    # Retry after a reply promised a later result with no lookup running.
    false_promise_retry: bool = False
    # Messages before the session idle gap (an older thread of this chat).
    earlier_messages: list[ContextMessage] | None = None
    # Schedule request outcome as a ready directive (see prompt_schedule).
    schedule_note: str | None = None
    channel_profile: ChannelProfile | None = None


_REQUEST_FIELDS = {field.name for field in fields(GenerateRequest)}


def as_generate_request(
    user_message: str | GenerateRequest,
    context_blocks: list[ContextBlock] | None = None,
    **kwargs: Any,
) -> GenerateRequest:
    """Pack a ``GenerateRequest`` or the legacy generate/prompt kwargs."""
    if isinstance(user_message, GenerateRequest):
        return user_message
    if context_blocks is None:
        raise TypeError(
            "generate() missing 1 required positional argument: 'context_blocks'"
        )
    extra = {key: value for key, value in kwargs.items() if key in _REQUEST_FIELDS}
    return GenerateRequest(
        user_message=user_message,
        context_blocks=context_blocks,
        **extra,
    )


def prompt_log_counts(request: GenerateRequest) -> tuple[int, int, int]:
    """Context message count, knowledge chars, and session chars for prompt logs."""
    message_count = sum(len(block.messages) for block in request.context_blocks)
    knowledge_chars = sum(
        len(block.content or "") for block in (request.knowledge_blocks or [])
    )
    session_chars = sum(
        len(message.content or "") for message in (request.session_messages or [])
    )
    return message_count, knowledge_chars, session_chars


__all__ = ["GenerateRequest", "as_generate_request", "prompt_log_counts"]
