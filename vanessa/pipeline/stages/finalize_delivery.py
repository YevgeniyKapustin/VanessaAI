from vanessa.config.content import get_content
from vanessa.pipeline.context import TurnPipelineContext
from vanessa.pipeline.llm.format.message_blocks import (
    split_reply_into_blocks,
    strip_block_markers,
)
from vanessa.pipeline.llm.format.reply_format import strip_trailing_periods
from vanessa.pipeline.llm.format.sticker_tag import extract_sticker_tag


def sticker_from_reply(ctx: TurnPipelineContext, reply: str) -> tuple[str, str | None]:
    clean, tag = extract_sticker_tag(reply)
    if not ctx.profile.stickers:
        return clean, None
    return clean, tag


def photo_fields(ctx: TurnPipelineContext) -> tuple[str | None, str | None]:
    if not ctx.profile.photos:
        return None, None
    return ctx.photo_file_id, ctx.photo_data_url


def delivery_messages(ctx: TurnPipelineContext, clean_reply: str) -> list[str]:
    marker = get_content().llm.block_marker
    if not ctx.profile.split_messages:
        text = strip_trailing_periods(strip_block_markers(clean_reply, marker=marker))
        if not text.strip():
            return []
        return [text]
    return [
        block
        for block in (
            strip_trailing_periods(b)
            for b in split_reply_into_blocks(clean_reply, marker=marker)
        )
        if block.strip()
    ]


def marker_free_reply(clean_reply: str) -> str:
    marker = get_content().llm.block_marker
    return strip_block_markers(clean_reply, marker=marker)
