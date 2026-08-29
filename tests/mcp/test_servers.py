import inspect
import socket
import threading

import uvicorn

from app.bot.services.obsidian_notes import ObsidianNoteService
from app.core.messages import WebResult
from app.knowledge.vault import KnowledgeVault
from app.mcp_server import knowledge, obsidian, vision, websearch


class _FakeSearch:
    async def search(self, query, *, limit=5):
        return [
            WebResult(
                title="Title",
                url="https://example.com",
                snippet="Snippet",
                published_date="2026-01-01",
            )
        ]


async def _names(server) -> set[str]:
    # mcp 1.x list_tools is sync; mcp 2.x returns a coroutine — handle both.
    tools = server.list_tools()
    if inspect.isawaitable(tools):
        tools = await tools
    return {tool.name for tool in tools}


async def test_websearch_server_registers_tool() -> None:
    server = websearch.build_server(provider=_FakeSearch())
    assert "web_search" in await _names(server)


async def test_knowledge_server_registers_tools(tmp_path) -> None:
    vault = KnowledgeVault(root_path=str(tmp_path))
    server = knowledge.build_server(vault=vault)
    assert {"vault_read", "vault_find"} <= await _names(server)


async def test_vision_server_registers_tool() -> None:
    server = vision.build_server()
    assert "describe_photo" in await _names(server)


async def test_obsidian_server_registers_tools() -> None:
    server = obsidian.build_server(
        service=ObsidianNoteService(vault_path="", git_enabled=False)
    )
    assert {"note_save", "note_status"} <= await _names(server)


async def test_servers_have_distinct_names() -> None:
    servers = [
        websearch.build_server(provider=_FakeSearch()),
        knowledge.build_server(vault=KnowledgeVault(root_path="")),
        vision.build_server(),
        obsidian.build_server(
            service=ObsidianNoteService(vault_path="", git_enabled=False)
        ),
    ]
    names = {server.name for server in servers}
    assert len(names) == 4


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 10.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(0.25)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.05)
    raise RuntimeError(f"port {port} never became ready")


async def test_knowledge_vault_find_over_http(tmp_path) -> None:
    """MCP contract test: the knowledge server resolves a person alias over the wire."""
    import json

    from app.mcp.client import StreamableHttpMcpClient

    vault = KnowledgeVault(root_path=str(tmp_path))
    await vault.ensure_structure()
    await vault.write_note("People/kraber.md", {"nickname": "Крабер"}, "Любит крабов и уток.")

    server = knowledge.build_server(vault=vault)
    server.streamable_http_path = "/mcp"
    app = server.streamable_http_app()
    port = _free_port()
    holder: dict = {}

    def run() -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        holder["server"] = uvicorn.Server(config)
        holder["server"].run()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    _wait_port(port)
    try:
        client = StreamableHttpMcpClient(f"http://127.0.0.1:{port}/mcp", timeout=10)
        raw = await client.call_tool("vault_find", {"name": "kraber"})
        assert "People/kraber.md" in raw
        assert "Любит крабов и уток." in raw
    finally:
        if "server" in holder:
            holder["server"].should_exit = True
            thread.join(timeout=5)
