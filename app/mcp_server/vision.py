"""MCP server: photo understanding (describe/caption).

Exposes ``describe_photo`` which returns a short Russian description of an
image passed as a base64 data URL (wraps the cheap DeepSeek vision model).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.messages import ImageAttachment
from app.llm.photo_captioner import PhotoCaptioner


def build_server(captioner: PhotoCaptioner | None = None) -> FastMCP:
    captioner = captioner if captioner is not None else PhotoCaptioner()
    server = FastMCP(
        name="vanessa-vision",
        instructions="Photo understanding for the Vanessa agent: short Russian "
        "descriptions of images passed as base64 data URLs.",
    )

    @server.tool(
        name="describe_photo",
        description=(
            "Return a short Russian description of a photo given as a base64 "
            "data URL. 'NO_CAPTION' when the model could not describe it."
        ),
    )
    async def describe_photo(data_url: str) -> str:
        if not data_url:
            return "NO_CAPTION"
        caption = await captioner.generate(ImageAttachment(data_url=data_url))
        return caption if caption else "NO_CAPTION"

    return server
