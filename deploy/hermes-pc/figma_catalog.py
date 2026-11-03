"""Bounded discovery of files inside configured Figma teams and folders."""

from figma_api import (
    DEFAULT_FILE,
    DEFAULT_NODE,
    FigmaApi,
    FigmaError,
    Settings,
    checked_depth,
    checked_id,
    checked_node,
    checked_search_depth,
    compact_node,
)
from figma_designs import search_nodes

MAX_FOLDERS = 50
MAX_FILES = 50


class FigmaCatalog:
    """Keep discovered folder and file permissions for this MCP process."""

    def __init__(self, settings: Settings, api: FigmaApi) -> None:
        self._settings = settings
        self._api = api
        self._folders = {
            checked_id(value, numeric=True) for value in settings.project_ids
        }
        self._files = {checked_id(value) for value in settings.file_keys}

    def list_team_projects(self, team_id: str = "") -> dict:
        teams = self._settings.team_ids
        if team_id:
            self._require_allowed(checked_id(team_id, numeric=True), teams, "команда")
            teams = {team_id}
        if not teams:
            raise FigmaError("Добавь FIGMA_TEAM_IDS в .env профиля Hermes.")
        folders = []
        for current in sorted(teams):
            checked_id(current, numeric=True)
            data = self._api.get(f"/v2/teams/{current}/folders")
            found = data.get("folders", [])
            self._remember_folders(found)
            folders.extend({**folder, "team_id": current} for folder in found)
        return {"folders": folders}

    def search_project_files(self, query: str = "", project_id: str = "") -> dict:
        roots = self._search_roots(project_id)
        pending = sorted(roots)
        visited = set()
        matches = []
        while pending and len(visited) < MAX_FOLDERS:
            folder = pending.pop(0)
            if folder in visited:
                continue
            visited.add(folder)
            matches.extend(self._folder_files(folder, query))
            pending.extend(self._subfolders(folder))
        return {
            "files": matches[:MAX_FILES],
            "folders_checked": len(visited),
            "truncated": bool(pending) or len(matches) > MAX_FILES,
        }

    def get_design_node(
        self, file_key: str = DEFAULT_FILE, node_id: str = DEFAULT_NODE, depth: int = 2
    ) -> dict:
        self._require_allowed(checked_id(file_key), self._files, "файл")
        node_id = checked_node(node_id)
        depth = checked_depth(depth)
        data = self._api.get(
            f"/v1/files/{file_key}/nodes", {"ids": node_id, "depth": depth}
        )
        entry = data.get("nodes", {}).get(node_id)
        if not entry or not entry.get("document"):
            raise FigmaError("Figma не нашла узел. Проверь node_id.")
        return {
            "file_name": data.get("name", ""),
            "url": f"https://www.figma.com/design/{file_key}/?node-id={node_id}",
            "document": compact_node(entry["document"]),
        }

    def get_file_outline(self, file_key: str = DEFAULT_FILE, depth: int = 2) -> dict:
        self._require_allowed(checked_id(file_key), self._files, "файл")
        data = self._api.get(f"/v1/files/{file_key}", {"depth": checked_depth(depth)})
        return {
            "file_name": data.get("name", ""),
            "document": compact_node(data["document"]),
        }

    def search_design_nodes(
        self,
        query: str,
        file_key: str = DEFAULT_FILE,
        *,
        include_text: bool = False,
        node_id: str = "",
        search_depth: int = 3,
    ) -> dict:
        self._require_allowed(checked_id(file_key), self._files, "файл")
        if not query.strip():
            raise FigmaError("Передай название экрана или текст для поиска.")
        search_depth = checked_search_depth(search_depth)
        data = self._search_data(file_key, node_id, search_depth)
        result = search_nodes(data, file_key, query.strip(), include_text=include_text)
        return {
            **result,
            "scope": {"file_key": file_key, "node_id": node_id, "depth": search_depth},
            "incomplete": True,
            "note": "Поиск ограничен глубиной. Отсутствие совпадения не означает отсутствие макета. Уточни страницу через node_id.",
        }

    def _search_data(self, file_key: str, node_id: str, depth: int) -> dict:
        if not node_id:
            return self._api.get(f"/v1/files/{file_key}", {"depth": depth})
        node_id = checked_node(node_id)
        data = self._api.get(
            f"/v1/files/{file_key}/nodes", {"ids": node_id, "depth": depth}
        )
        entry = data.get("nodes", {}).get(node_id)
        if not entry or not entry.get("document"):
            raise FigmaError("Figma не нашла узел. Проверь node_id.")
        return {"name": data.get("name", ""), "document": entry["document"]}

    def _search_roots(self, project_id: str) -> set[str]:
        if project_id:
            self._require_allowed(
                checked_id(project_id, numeric=True), self._folders, "папка"
            )
            return {project_id}
        if self._settings.team_ids:
            self.list_team_projects()
        if not self._folders:
            raise FigmaError("Добавь FIGMA_PROJECT_IDS или FIGMA_TEAM_IDS в .env.")
        return set(self._folders)

    def _folder_files(self, folder: str, query: str) -> list[dict]:
        data = self._api.get(f"/v2/folders/{folder}/files")
        files = data.get("files", [])
        self._files.update(checked_id(file["key"]) for file in files)
        return [
            {
                "key": file["key"],
                "name": file["name"],
                "project_id": folder,
                "url": f"https://www.figma.com/design/{file['key']}/",
            }
            for file in files
            if query.casefold() in file["name"].casefold()
        ]

    def _subfolders(self, folder: str) -> list[str]:
        data = self._api.get(f"/v2/folders/{folder}/folders")
        found = data.get("folders", [])
        self._remember_folders(found)
        return [str(item["id"]) for item in found]

    def _remember_folders(self, folders: list[dict]) -> None:
        self._folders.update(
            checked_id(str(item["id"]), numeric=True) for item in folders
        )

    @staticmethod
    def _require_allowed(value: str, allowed: set[str], kind: str) -> None:
        if value not in allowed:
            raise FigmaError(
                f"Этот {kind} не разрешён. Используй поиск или настрой allowlist в .env."
            )
