from vanessa.config.settings import settings
from vanessa.core.messages import ImageAttachment
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.stages.photos_album import _collect_photo_candidates

__all__ = ["_collect_photo_candidates", "_collect_turn_images"]


def _collect_turn_images(ctx: TurnPipelineContext) -> list[ImageAttachment]:
    """Assemble the images for a vision turn.

    Current-turn images come first; then attachments from prior session messages
    (newest first, excluding the current message — it already contributes via
    ``ctx.turn.images``) so a follow-up can reference an earlier photo.
    Bounded by ``vision_session_images`` per session and
    ``vision_max_images_per_turn`` overall.
    """
    images: list[ImageAttachment] = list(ctx.turn.images)
    prior = ctx.recent[:-1] if ctx.recent else []
    _extend_prior_session_images(
        images,
        prior,
        session_limit=settings.vision_session_images,
        max_total=settings.vision_max_images_per_turn,
    )
    return images[: settings.vision_max_images_per_turn]


def _extend_prior_session_images(
    images: list[ImageAttachment],
    prior,
    *,
    session_limit: int,
    max_total: int,
) -> None:
    session_count = 0
    for message in reversed(prior):
        if session_count >= session_limit or len(images) >= max_total:
            break
        session_count += _append_message_session_images(
            images,
            message,
            session_count=session_count,
            session_limit=session_limit,
            max_total=max_total,
        )


def _append_message_session_images(
    images: list[ImageAttachment],
    message,
    *,
    session_count: int,
    session_limit: int,
    max_total: int,
) -> int:
    added = 0
    for attachment in message.attachments:
        if not attachment.data_url:
            continue
        images.append(attachment)
        added += 1
        if session_count + added >= session_limit or len(images) >= max_total:
            break
    return added
