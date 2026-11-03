"""Exercise the PC MCP's API boundary and discovery without live credentials."""

import importlib
from pathlib import Path

import httpx
import pytest

PC_SCRIPTS = Path(__file__).resolve().parents[2] / "deploy" / "hermes-pc"
TEST_TOKEN = "test-token"
EXPECTED_SEARCH_FOLDERS = 2


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(PC_SCRIPTS))
    api = importlib.import_module("figma_api")
    # The repo ships no real file key; tests pin their own.
    monkeypatch.setattr(api, "DEFAULT_FILE", "testfilekey")
    return api, importlib.import_module("figma_catalog")


def make_catalog(modules, handler, *, token=TEST_TOKEN, teams=(), projects=()):
    api, catalog = modules
    client = httpx.Client(
        base_url="https://api.figma.com",
        headers={"X-Figma-Token": token},
        transport=httpx.MockTransport(handler),
    )
    settings = api.Settings(token, set(teams), set(projects), {api.DEFAULT_FILE})
    return catalog.FigmaCatalog(settings, api.FigmaApi(token, client))


def test_default_node_reads_only_expected_endpoint(modules):
    api, _ = modules

    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "api.figma.com"
        assert request.url.path == f"/v1/files/{api.DEFAULT_FILE}/nodes"
        assert dict(request.url.params) == {"ids": api.DEFAULT_NODE, "depth": "2"}
        assert request.headers["X-Figma-Token"] == "test-token"
        return httpx.Response(
            200,
            json={
                "nodes": {
                    api.DEFAULT_NODE: {
                        "document": {
                            "id": api.DEFAULT_NODE,
                            "name": "Checkout",
                            "type": "FRAME",
                            "children": [
                                {"id": "1:2", "characters": "Pay", "ignored": "hidden"}
                            ],
                        }
                    }
                }
            },
        )

    result = make_catalog(modules, handler).get_design_node(node_id="12188-511735")
    assert result["document"]["name"] == "Checkout"
    assert result["document"]["children"] == [{"id": "1:2", "characters": "Pay"}]


@pytest.mark.parametrize(
    "arguments",
    [
        {"file_key": "https://example.com"},
        {"file_key": "OtherFile"},
        {"node_id": "../../me"},
        {"node_id": "1:2&ids=3:4"},
        {"depth": 0},
        {"depth": 4},
        {"depth": True},
        {"depth": 1.5},
    ],
)
def test_rejects_unallowed_identifiers_and_depth_before_network(modules, arguments):
    def handler(_request):
        pytest.fail("Invalid input reached the network")

    api, _ = modules
    with pytest.raises(api.FigmaError):
        make_catalog(modules, handler).get_design_node(**arguments)


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "токен"),
        (403, "доступ"),
        (404, "не нашла"),
        (429, "ограничила"),
        (502, "HTTP 502"),
        (302, "HTTP 302"),
    ],
)
def test_http_errors_hide_response_body(modules, status, message):
    api, _ = modules
    reader = make_catalog(
        modules, lambda _request: httpx.Response(status, json={"err": "secret-body"})
    )
    with pytest.raises(api.FigmaError, match=message) as caught:
        reader.get_design_node()
    assert "secret-body" not in str(caught.value)


def test_missing_auth_does_not_send_request(modules):
    def handler(_request):
        pytest.fail("Unauthenticated request reached the network")

    api, _ = modules
    with pytest.raises(api.FigmaError, match="FIGMA_ACCESS_TOKEN"):
        make_catalog(modules, handler, token="").get_design_node()


def test_network_failure_and_invalid_json_have_clear_errors(modules):
    api, _ = modules

    def handler(request):
        raise httpx.ConnectError("failed", request=request)

    with pytest.raises(api.FigmaError, match="недоступен"):
        make_catalog(modules, handler).get_design_node()
    with pytest.raises(api.FigmaError, match="JSON"):
        make_catalog(
            modules, lambda _request: httpx.Response(200, text="invalid")
        ).get_design_node()


def test_missing_node_has_clear_error(modules):
    api, _ = modules
    with pytest.raises(api.FigmaError, match="не нашла узел"):
        make_catalog(
            modules, lambda _request: httpx.Response(200, json={"nodes": {}})
        ).get_design_node()


def test_team_search_discovers_nested_files_and_permits_reading_them(modules):
    requests = []
    payloads = {
        "/v2/teams/10/folders": {"folders": [{"id": "20", "name": "Product"}]},
        "/v2/folders/20/files": {"files": [{"key": "MainFile", "name": "Home"}]},
        "/v2/folders/20/folders": {"folders": [{"id": "21", "name": "Payments"}]},
        "/v2/folders/21/files": {"files": [{"key": "PayFile", "name": "CHECKOUT"}]},
        "/v2/folders/21/folders": {"folders": []},
        "/v1/files/PayFile": {"document": {"id": "0:0", "type": "DOCUMENT"}},
    }

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, json=payloads[request.url.path])

    reader = make_catalog(modules, handler, teams=["10"])
    result = reader.search_project_files("checkout")
    assert result["files"] == [
        {
            "key": "PayFile",
            "name": "CHECKOUT",
            "project_id": "21",
            "url": "https://www.figma.com/design/PayFile/",
        }
    ]
    assert result["folders_checked"] == EXPECTED_SEARCH_FOLDERS
    assert not result["truncated"]
    assert reader.get_file_outline("PayFile")["document"]["id"] == "0:0"
    assert all(path.startswith(("/v1/", "/v2/")) for path in requests)


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("list_team_projects", "99"),
        ("list_team_projects", "../../me"),
        ("search_project_files", "99"),
        ("search_project_files", "https://example.com"),
    ],
)
def test_discovery_requires_allowed_teams_and_projects(modules, method, value):
    api, _ = modules
    reader = make_catalog(modules, lambda _request: pytest.fail("Unexpected request"))
    arguments = (
        {"team_id": value} if method == "list_team_projects" else {"project_id": value}
    )
    with pytest.raises(api.FigmaError):
        getattr(reader, method)(**arguments)


def test_design_search_works_without_team_scope_and_finds_ui_text(modules):
    payload = {
        "name": "Work chat",
        "document": {
            "id": "0:0",
            "name": "Root",
            "children": [
                {"id": "1:1", "name": "Checkout", "type": "FRAME"},
                {"id": "1:2", "name": "Label", "type": "TEXT", "characters": "PAY NOW"},
            ],
        },
    }

    def handler(request):
        assert request.url.params["depth"] == "3"
        return httpx.Response(200, json=payload)

    reader = make_catalog(modules, handler)
    names = reader.search_design_nodes("checkout")
    assert [node["id"] for node in names["nodes"]] == ["1:1"]
    assert names["incomplete"]
    assert names["scope"] == {
        "file_key": modules[0].DEFAULT_FILE,
        "node_id": "",
        "depth": 3,
    }
    assert not reader.search_design_nodes("pay")["nodes"]
    assert (
        reader.search_design_nodes("pay", include_text=True)["nodes"][0]["text"]
        == "PAY NOW"
    )


def test_page_scoped_search_limits_request_and_returns_honest_scope(modules):
    api, _ = modules

    def handler(request):
        assert request.url.path.endswith("/nodes")
        assert dict(request.url.params) == {"ids": "10:20", "depth": "5"}
        return httpx.Response(
            200,
            json={
                "nodes": {
                    "10:20": {
                        "document": {
                            "id": "10:20",
                            "name": "Payments",
                            "type": "CANVAS",
                        }
                    }
                }
            },
        )

    result = make_catalog(modules, handler).search_design_nodes(
        "unknown screen", node_id="10:20", search_depth=5
    )
    assert not result["nodes"]
    assert result["incomplete"]
    assert result["scope"] == {
        "file_key": api.DEFAULT_FILE,
        "node_id": "10:20",
        "depth": 5,
    }
    assert "не означает" in result["note"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": " "},
        {"query": "x", "file_key": "Other"},
        {"query": "x", "node_id": "https://example.com"},
        {"query": "x", "search_depth": 2},
        {"query": "x", "search_depth": 6},
        {"query": "x", "search_depth": True},
    ],
)
def test_search_rejects_invalid_scope_before_network(modules, arguments):
    api, _ = modules
    reader = make_catalog(modules, lambda _request: pytest.fail("Unexpected request"))
    with pytest.raises(api.FigmaError):
        reader.search_design_nodes(**arguments)


def test_node_search_stops_at_scan_limit(modules, monkeypatch):
    designs = importlib.import_module("figma_designs")
    monkeypatch.setattr(designs, "MAX_SEARCH_NODES", 1)
    payload = {
        "document": {
            "id": "0:0",
            "name": "Root",
            "children": [
                {"id": "1:1", "name": "Checkout"},
            ],
        }
    }
    reader = make_catalog(modules, lambda _request: httpx.Response(200, json=payload))
    result = reader.search_design_nodes("checkout")
    assert result["nodes_checked"] == 1
    assert result["truncated"]
    assert not result["nodes"]


def test_folder_search_stops_at_folder_limit(modules, monkeypatch):
    _, catalog = modules
    monkeypatch.setattr(catalog, "MAX_FOLDERS", 1)
    payloads = {
        "/v2/folders/20/files": {"files": []},
        "/v2/folders/20/folders": {"folders": [{"id": "21", "name": "Child"}]},
    }
    reader = make_catalog(
        modules,
        lambda request: httpx.Response(200, json=payloads[request.url.path]),
        projects=["20"],
    )
    assert reader.search_project_files()["truncated"]


def test_api_does_not_follow_redirect_with_token(modules, monkeypatch):
    api, _ = modules
    client_class = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://example.com/stolen"})

    def make_client(**kwargs):
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(api.httpx, "Client", make_client)
    reader = api.make_api(TEST_TOKEN)
    with pytest.raises(api.FigmaError, match="HTTP 302"):
        reader.get("/v1/files/Example")
    assert len(requests) == 1
    assert requests[0].url.host == "api.figma.com"


async def test_mcp_exposes_only_the_five_read_tools(modules):
    server_module = importlib.import_module("figma_mcp")
    reader = make_catalog(modules, lambda _request: pytest.fail("Unexpected request"))
    tools = await server_module.build_server(reader).list_tools()
    assert {tool.name for tool in tools} == {
        "list_team_projects",
        "search_project_files",
        "search_design_nodes",
        "get_file_outline",
        "get_design_node",
    }


def test_profile_env_and_token_alias_are_loaded(modules, monkeypatch, tmp_path):
    api, _ = modules
    for name in (
        "FIGMA_ACCESS_TOKEN",
        "FIGMA_TOKEN",
        "FIGMA_TEAM_IDS",
        "FIGMA_PROJECT_IDS",
        "FIGMA_FILE_KEYS",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FIGMA_TOKEN=test-only\nFIGMA_TEAM_IDS=10, 11\nFIGMA_PROJECT_IDS=20\nFIGMA_FILE_KEYS=Other\n"
    )
    monkeypatch.setenv("FIGMA_ENV_FILE", str(env_file))
    settings = api.settings_from_env()
    assert settings.token == "test-only"
    assert settings.team_ids == {"10", "11"}
    assert settings.project_ids == {"20"}
    assert settings.file_keys == {api.DEFAULT_FILE, "Other"}
