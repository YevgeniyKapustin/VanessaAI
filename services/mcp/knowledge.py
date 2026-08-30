"""MCP server: the knowledge vault (read/search by name).

Exposes ``vault_read`` (direct note read by relative path) and ``vault_find``
(name resolution across the People/Lore/Culture/inbox folders). Semantic
embedding search stays in the agent core; this server is the "memory" tool.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from vanessa.knowledge.vault import KnowledgeVault

# Folders checked by ``vault_find``, in priority order.
_SEARCH_FOLDERS = (
    "People",
    "Lore/glossary",
    "Lore/events",
    "Culture",
    "inbox",
)


def _candidates(name: str) -> list[str]:
    clean = name.strip().strip("/")
    if not clean:
        return []
    if "/" in clean:  # explicit relative path — let vault_read handle it
        return []
    return [f"{folder}/{clean}.md" for folder in _SEARCH_FOLDERS]


def build_server(vault: KnowledgeVault | None = None) -> FastMCP:
    vault = vault if vault is not None else KnowledgeVault()
    server = FastMCP(
        name="vanessa-knowledge",
        instructions="Structured memory of the Vanessa agent: People dossiers, "
        "chat lore, culture, inbox. Read-only.",
    )

    @server.tool(
        name="vault_read",
        description=(
            "Read a knowledge-vault note by its relative path "
            "(e.g. 'People/kraber.md'). Returns the note body, or 'NOT FOUND'."
        ),
    )
    async def vault_read(relative_path: str) -> str:
        note = await vault.read_note(relative_path)
        if note is None:
            return f"NOT FOUND: {relative_path}"
        return note.body if note.body else "(empty note)"

    @server.tool(
        name="vault_find",
        description=(
            "Find a note by a person/glossary/event/culture name across the "
            "vault folders. Returns the first matching note body, or 'NOT FOUND'."
        ),
    )
    async def vault_find(name: str) -> str:
        for relative_path in _candidates(name):
            note = await vault.read_note(relative_path)
            if note is not None:
                return f"{relative_path}\n---\n{note.body}"
        return f"NOT FOUND: {name}"

    return server
