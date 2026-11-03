"""Local stdio MCP for finding and reading the team's Figma designs."""

from figma_api import make_api, settings_from_env
from figma_catalog import FigmaCatalog
from mcp.server.fastmcp import FastMCP


def build_server(catalog: FigmaCatalog) -> FastMCP:
    server = FastMCP("vanessa-figma-readonly")

    server.add_tool(
        catalog.list_team_projects,
        description="List allowed Figma team projects/folders. Empty ID lists configured teams.",
    )
    server.add_tool(
        catalog.search_project_files,
        description="Find design files by name in allowed projects and subfolders. Empty project_id searches configured teams/projects; empty query lists files. At most 50 folders/files.",
    )
    server.add_tool(
        catalog.search_design_nodes,
        description="Find screen/frame/layer names inside a known file. Search the default design file first. search_depth=3..5 bounds each request; optional node_id narrows to a page/frame. include_text searches UI text in that scope. Results are incomplete: no match never proves absence. Use get_file_outline to choose pages. At most 50 results / 50000 checked nodes. Requires file_content:read only, no team IDs.",
    )
    server.add_tool(
        catalog.get_file_outline,
        description="List pages and frames of a known file to find node IDs. depth is 1 to 3.",
    )
    server.add_tool(
        catalog.get_design_node,
        description="Read node text, dimensions, styling and layout. Pass node_id from a Figma link, e.g. 12188-511735. depth is 1 to 3. Only known or discovered files are allowed. Cannot modify files or comments.",
    )
    return server


def main() -> None:
    settings = settings_from_env()
    catalog = FigmaCatalog(settings, make_api(settings.token))
    build_server(catalog).run(transport="stdio")


if __name__ == "__main__":
    main()
