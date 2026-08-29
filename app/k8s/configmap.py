from __future__ import annotations

from typing import Mapping

from app.k8s.secrets import SECRET_KEYS

CONFIGMAP_NAME = "vanessa-config"

COMPOSE_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "REDIS_AUTH",
        "LANGFUSE_REDIS_AUTH",
        "COMPOSE_FILE",
        "LANGFUSE_DB_USER",
        "LANGFUSE_DB_PASSWORD",
        "LANGFUSE_DB_NAME",
        "LANGFUSE_NEXTAUTH_URL",
        "LANGFUSE_NEXTAUTH_SECRET",
        "LANGFUSE_SALT",
        "LANGFUSE_ENCRYPTION_KEY",
        "CLICKHOUSE_DB",
        "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "API_PORT",
        "API_WORKERS",
        "API_GRACEFUL_TIMEOUT",
        "NGINX_HTTP_PORT",
        "OBSIDIAN_VAULT_HOST_PATH",
        "OBSIDIAN_SSH_DIR",
    }
)

CLUSTER_OVERRIDES: dict[str, str] = {
    "TRANSPORT": "redis",
    "WORKER_ENABLED": "true",
    "MCP_WEBSEARCH_URL": "http://mcp-websearch:8101/mcp",
    "MCP_KNOWLEDGE_URL": "http://mcp-knowledge:8102/mcp",
    "MCP_VISION_URL": "http://mcp-vision:8103/mcp",
}


def select_config_values(
    env: Mapping[str, str],
    *,
    postgres_host: str | None = None,
    qdrant_host: str | None = None,
    langfuse_host: str | None = None,
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in env.items():
        if key in SECRET_KEYS or key in COMPOSE_ONLY_KEYS:
            continue
        stripped = value.strip()
        if stripped:
            selected[key] = stripped
    selected.update(CLUSTER_OVERRIDES)
    if postgres_host:
        selected["POSTGRES_HOST"] = postgres_host
    if qdrant_host:
        selected["QDRANT_HOST"] = qdrant_host
    if langfuse_host:
        selected["LANGFUSE_HOST"] = langfuse_host
    return dict(sorted(selected.items()))


def build_configmap(*, namespace: str, values: Mapping[str, str]) -> dict:
    if not values:
        raise ValueError("configmap values must not be empty")
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": CONFIGMAP_NAME,
            "namespace": namespace,
            "labels": {
                "app": "vanessa",
                "app.kubernetes.io/part-of": "vanessa",
                "app.kubernetes.io/component": "config",
            },
        },
        "data": dict(values),
    }
