"""Search names and text inside an already allowed Figma design file."""

from collections.abc import Iterator

MAX_SEARCH_NODES = 50000
MAX_MATCHES = 50


def _walk_nodes(document: dict) -> Iterator[tuple[dict, str]]:
    pending = [(document, "")]
    while pending:
        node, parent = pending.pop()
        path = f"{parent}/{node.get('name', '')}"
        yield node, path
        pending.extend((child, path) for child in reversed(node.get("children", [])))


def _matches(node: dict, query: str, *, include_text: bool) -> bool:
    if query in node.get("name", "").casefold():
        return True
    return include_text and query in node.get("characters", "").casefold()


def search_nodes(data: dict, file_key: str, query: str, *, include_text: bool) -> dict:
    matches = []
    scanned = 0
    truncated = False
    for node, path in _walk_nodes(data["document"]):
        if scanned >= MAX_SEARCH_NODES or len(matches) >= MAX_MATCHES:
            truncated = True
            break
        scanned += 1
        if _matches(node, query.casefold(), include_text=include_text):
            matches.append(_node_match(node, path, file_key))
    return {
        "file_name": data.get("name", ""),
        "nodes": matches,
        "nodes_checked": scanned,
        "truncated": truncated,
    }


def _node_match(node: dict, path: str, file_key: str) -> dict:
    node_id = node["id"]
    return {
        "id": node_id,
        "name": node.get("name", ""),
        "type": node.get("type", ""),
        "path": path,
        "text": node.get("characters", "")[:200],
        "url": f"https://www.figma.com/design/{file_key}/?node-id={node_id}",
    }
