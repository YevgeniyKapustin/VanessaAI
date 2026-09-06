from vanessa.config.content import get_photo_placeholder
from vanessa.config.settings import settings
from vanessa.core.messages import ContextMessage, PhotoCandidate
from vanessa.pipeline.context import TurnPipelineContext


def _photo_caption_for(message) -> str:
    """Visual label of a photo for the album ``<description>``.

    Only the vision-generated ``photo_caption`` belongs here. The user's
    Telegram caption is message text (``<text>``), not a picture label —
    stuffing it into ``<description>`` makes the model treat a question as
    "what is on the photo".
    """
    if message.photo_caption and message.photo_caption.strip():
        return message.photo_caption.strip()
    return get_photo_placeholder()


def _append_photo_from_message(
    message,
    *,
    seen: set[str],
    current_file_ids: set[str],
    collected: list[tuple[str, str, str, str, object]],
) -> None:
    for attachment in message.attachments:
        file_id = attachment.telegram_file_id
        if not file_id or file_id in seen or file_id in current_file_ids:
            continue
        seen.add(file_id)
        collected.append(
            (
                file_id,
                attachment.data_url or "",
                _photo_caption_for(message),
                message.sender_name or "",
                message,
            )
        )


def _current_turn_file_ids(ctx: TurnPipelineContext) -> set[str]:
    return {
        attachment.telegram_file_id
        for attachment in ctx.turn.images
        if attachment.telegram_file_id
    }


def _append_photos_from_context(
    ctx: TurnPipelineContext,
    *,
    seen: set[str],
    current_file_ids: set[str],
    collected: list[tuple[str, str, str, str, object]],
) -> None:
    for block in ctx.context_blocks:
        for message in block.messages:
            _append_photo_from_message(
                message,
                seen=seen,
                current_file_ids=current_file_ids,
                collected=collected,
            )


def _collect_photo_rows(
    ctx: TurnPipelineContext,
    photo_messages: list[ContextMessage] | None,
) -> list[tuple[str, str, str, str, object]]:
    seen: set[str] = set()
    collected: list[tuple[str, str, str, str, object]] = []
    # The current turn's own images are already attached (``current_images`` /
    # ``images``) — never offer them again as re-sendable album entries.
    current_file_ids = _current_turn_file_ids(ctx)
    # Meaning-search hits first (the strongest "по смыслу" match), then the RAG
    # context (meaning match), then the recent session (recency).
    for message in photo_messages or []:
        _append_photo_from_message(
            message,
            seen=seen,
            current_file_ids=current_file_ids,
            collected=collected,
        )
    _append_photos_from_context(
        ctx,
        seen=seen,
        current_file_ids=current_file_ids,
        collected=collected,
    )
    for message in ctx.recent:
        _append_photo_from_message(
            message,
            seen=seen,
            current_file_ids=current_file_ids,
            collected=collected,
        )
    return collected


def _photo_candidates_from_rows(
    collected: list[tuple[str, str, str, str, object]],
) -> list[PhotoCandidate]:
    candidates: list[PhotoCandidate] = []
    for index, (file_id, data_url, caption, sender, message) in enumerate(
        collected, start=1
    ):
        if len(candidates) >= settings.vision_photo_candidates:
            break
        candidates.append(
            PhotoCandidate(
                index=index,
                telegram_file_id=file_id,
                caption=caption,
                sender_name=sender or None,
                created_at=getattr(message, "created_at", None),
                data_url=data_url or None,
            )
        )
    return candidates


def _collect_photo_candidates(
    ctx: TurnPipelineContext,
    photo_messages: list[ContextMessage] | None = None,
) -> list[PhotoCandidate]:
    """Assemble the "photo album" — photos the bot could re-send.

    Candidates come from three sources, all meaning-driven:
    - ``photo_messages`` — the dedicated photo-by-meaning search
      (``search_photo_messages`` FTS over the caption-inclusive search_vector)
      run against the REWRITTEN query, so a photo is found by the MEANING of
      the turn ("скинь то фото где кот" -> the caption "рыжий кот на диване"),
      not by the literal words the user typed;
    - messages the RAG retrieval surfaced for THIS turn (``ctx.context_blocks``) —
      the "по смыслу" leg (photo captions are folded into the FTS search_vector);
    - recent session messages with attachments (so "верни то фото" without a
      precise query still works).
    Deduplicated by telegram_file_id and bounded by ``vision_photo_candidates``.
    """
    collected = _collect_photo_rows(ctx, photo_messages)
    return _photo_candidates_from_rows(collected)
