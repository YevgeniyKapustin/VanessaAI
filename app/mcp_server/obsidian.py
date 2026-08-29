"""MCP server: Obsidian vault notes (read/write).

Exposes ``note_save`` (write a note into the configured Obsidian vault with
the same naming/git behavior as the bot's note handler).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.bot.services.obsidian_notes import ObsidianNoteService


def build_server(service: ObsidianNoteService | None = None) -> FastMCP:
    service = service if service is not None else ObsidianNoteService()
    server = FastMCP(
        name="vanessa-obsidian",
        instructions="Write notes into the Vanessa Obsidian vault.",
    )

    @server.tool(
        name="note_save",
        description=(
            "Save a text note into the Obsidian vault (with a timestamped "
            "filename and optional git commit). Returns the saved relative path."
        ),
    )
    async def note_save(text: str) -> str:
        if not text.strip():
            return "ERROR: empty note"
        if not service.is_configured:
            return "ERROR: obsidian vault is not configured"
        saved = await service.save_note(text)
        return saved.relative_path

    @server.tool(
        name="note_status",
        description="Return whether the Obsidian vault is configured.",
    )
    async def note_status() -> str:
        return "configured" if service.is_configured else "not_configured"

    return server
