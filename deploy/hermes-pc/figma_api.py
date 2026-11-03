"""Read-only Figma REST requests and compact design-node output."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

#: The design file the tools read when no key is given. It is not a secret,
#: but it identifies the team's working file, so it stays out of the repo:
#: set FIGMA_DEFAULT_FILE (or FIGMA_FILE_KEYS) in the profile env.
DEFAULT_FILE = ""
DEFAULT_NODE = "12188:511735"
MAX_NODE_DEPTH = 3
MIN_SEARCH_DEPTH = 3
MAX_SEARCH_DEPTH = 5
NODE_FIELDS = (
    "id",
    "name",
    "type",
    "characters",
    "absoluteBoundingBox",
    "layoutMode",
    "primaryAxisSizingMode",
    "counterAxisSizingMode",
    "itemSpacing",
    "paddingLeft",
    "paddingRight",
    "paddingTop",
    "paddingBottom",
    "style",
    "fills",
    "strokes",
    "effects",
    "opacity",
    "cornerRadius",
)


class FigmaError(ValueError):
    """A safe error message that contains no API token or response body."""


@dataclass(frozen=True)
class Settings:
    token: str
    team_ids: set[str]
    project_ids: set[str]
    file_keys: set[str]


def _env_ids(name: str) -> set[str]:
    values = {value.strip() for value in os.environ.get(name, "").split(",")}
    return {value for value in values if value}


def settings_from_env() -> Settings:
    env_file = os.environ.get("FIGMA_ENV_FILE", "")
    if env_file:
        load_dotenv(Path(env_file), override=True)
    file_keys = _env_ids("FIGMA_FILE_KEYS")
    default_file = DEFAULT_FILE or os.environ.get("FIGMA_DEFAULT_FILE", "").strip()
    if default_file:
        file_keys.add(default_file)
    return Settings(
        token=(
            os.environ.get("FIGMA_ACCESS_TOKEN") or os.environ.get("FIGMA_TOKEN", "")
        ).strip(),
        team_ids=_env_ids("FIGMA_TEAM_IDS"),
        project_ids=_env_ids("FIGMA_PROJECT_IDS"),
        file_keys=file_keys,
    )


def checked_id(value: str, *, numeric: bool = False) -> str:
    pattern = r"[0-9]+" if numeric else r"[A-Za-z0-9]+"
    if not re.fullmatch(pattern, value):
        raise FigmaError("Передай ID Figma, а не URL или путь.")
    return value


def checked_node(value: str) -> str:
    value = value.replace("-", ":")
    if not re.fullmatch(r"[0-9]+:[0-9]+", value):
        raise FigmaError("Передай node_id вида 12188:511735 или 12188-511735.")
    return value


def checked_depth(depth: int) -> int:
    if type(depth) is not int or not 1 <= depth <= MAX_NODE_DEPTH:
        raise FigmaError("depth должен быть целым числом от 1 до 3.")
    return depth


def checked_search_depth(depth: int) -> int:
    if type(depth) is not int or not MIN_SEARCH_DEPTH <= depth <= MAX_SEARCH_DEPTH:
        raise FigmaError("search_depth должен быть целым числом от 3 до 5.")
    return depth


def compact_node(node: dict) -> dict:
    result = {key: node[key] for key in NODE_FIELDS if key in node}
    if "children" in node:
        result["children"] = [compact_node(child) for child in node["children"]]
    return result


class FigmaApi:
    """HTTP client boundary; supports only authenticated GET requests."""

    def __init__(self, token: str, client: httpx.Client) -> None:
        self._token = token
        self._client = client

    def get(self, path: str, params: dict | None = None) -> dict:
        if not self._token:
            raise FigmaError("Добавь FIGMA_ACCESS_TOKEN в .env профиля Hermes.")
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise FigmaError(
                "Figma API недоступен. Проверь сеть и повтори запрос."
            ) from exc
        self._check_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise FigmaError("Figma API вернул некорректный JSON.") from exc

    def _check_status(self, response: httpx.Response) -> None:
        messages = {
            401: "Figma отклонила токен. Проверь FIGMA_ACCESS_TOKEN.",
            403: "Figma запретила доступ. Проверь токен, scopes и доступ к дизайну.",
            404: "Figma не нашла файл, узел или папку. Проверь ID и доступ.",
            429: "Figma ограничила запросы. Повтори позже; автоматического повтора нет.",
        }
        if response.status_code in messages:
            raise FigmaError(messages[response.status_code])
        if not response.is_success:
            raise FigmaError(f"Figma API: HTTP {response.status_code}.")


def make_api(token: str) -> FigmaApi:
    client = httpx.Client(
        base_url="https://api.figma.com",
        headers={"X-Figma-Token": token},
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    )
    return FigmaApi(token, client)
