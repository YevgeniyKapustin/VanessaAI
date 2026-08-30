from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import yaml
from dotenv import dotenv_values

SECRET_NAME = "vanessa-secrets"
DEFAULT_NAMESPACE = "vanessa"
IMAGE = "vanessa-agent:local"

SECRET_KEYS: frozenset[str] = frozenset(
    {
        "TELEGRAM_BOT_TOKEN",
        "POSTGRES_PASSWORD",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "WEB_SEARCH_API_KEY",
        "API_INTERNAL_TOKEN",
        "HF_TOKEN",
        "BROKER_REDIS_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_ID_SALT",
    }
)

ALWAYS_REQUIRED: frozenset[str] = frozenset(
    {
        "TELEGRAM_BOT_TOKEN",
        "POSTGRES_PASSWORD",
        "BROKER_REDIS_URL",
    }
)

OPTIONAL_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "WEB_SEARCH_API_KEY",
        "API_INTERNAL_TOKEN",
        "HF_TOKEN",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_ID_SALT",
    }
)

# Keys injected per workload. Missing optional keys use secretKeyRef.optional.
WORKLOAD_SECRET_KEYS: dict[str, frozenset[str]] = {
    "migrate": frozenset({"POSTGRES_PASSWORD"}),
    "agent": frozenset(
        {
            "TELEGRAM_BOT_TOKEN",
            "POSTGRES_PASSWORD",
            "BROKER_REDIS_URL",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
            "API_INTERNAL_TOKEN",
            "HF_TOKEN",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_ID_SALT",
        }
    ),
    "bot": frozenset(
        {
            "TELEGRAM_BOT_TOKEN",
            "BROKER_REDIS_URL",
            "API_INTERNAL_TOKEN",
        }
    ),
    "worker": frozenset(
        {
            "POSTGRES_PASSWORD",
            "BROKER_REDIS_URL",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
            "HF_TOKEN",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_ID_SALT",
        }
    ),
    "mcp-websearch": frozenset({"WEB_SEARCH_API_KEY"}),
    "mcp-knowledge": frozenset({"POSTGRES_PASSWORD"}),
    "mcp-vision": frozenset({"DEEPSEEK_API_KEY"}),
}

_TRUE = frozenset({"1", "true", "yes", "on"})

_PART_OF_LABELS = {
    "app": "vanessa",
    "vanessa.kubernetes.io/part-of": "vanessa",
    "vanessa.kubernetes.io/component": "secrets",
}


class SecretsValidationError(ValueError):
    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        joined = ", ".join(missing)
        super().__init__(f"missing required secret keys: {joined}")


@dataclass(frozen=True, slots=True)
class SecretPlan:
    values: dict[str, str]
    required: frozenset[str]
    missing: tuple[str, ...]
    present: tuple[str, ...]
    optional_absent: tuple[str, ...]


def fill_broker_url(env: Mapping[str, str]) -> dict[str, str]:
    merged = {key: value for key, value in env.items()}
    if merged.get("BROKER_REDIS_URL", "").strip():
        return merged
    auth = merged.get("REDIS_AUTH", "").strip()
    if not auth:
        return merged
    merged["BROKER_REDIS_URL"] = f"redis://:{quote(auth, safe='')}@redis:6379/0"
    return merged


def rewrite_broker_host(
    url: str,
    host: str,
    *,
    password: str | None = None,
) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError("BROKER_REDIS_URL has no hostname")
    resolved = password if password is not None else parsed.password
    if resolved is not None or parsed.username:
        user = parsed.username or ""
        secret = quote(resolved or "", safe="")
        userinfo = f"{user}:{secret}@"
    else:
        userinfo = ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{userinfo}{host}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def load_env_file(path: Path) -> dict[str, str]:
    raw = dotenv_values(path)
    loaded: dict[str, str] = {}
    for key, value in raw.items():
        if not key or value is None:
            continue
        stripped = value.strip()
        if stripped:
            loaded[key] = stripped
    return loaded


def select_secret_values(env: Mapping[str, str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key in sorted(SECRET_KEYS):
        value = env.get(key, "").strip()
        if value:
            selected[key] = value
    return selected


def required_keys_for(env: Mapping[str, str]) -> frozenset[str]:
    required = set(ALWAYS_REQUIRED)
    provider = env.get("LLM_PROVIDER", "deepseek").strip().lower()
    if provider == "claude":
        required.add("ANTHROPIC_API_KEY")
    else:
        required.add("DEEPSEEK_API_KEY")
    web_enabled = env.get("WEB_SEARCH_ENABLED", "").strip().lower() in _TRUE
    web_provider = env.get("WEB_SEARCH_PROVIDER", "tavily").strip().lower()
    if web_enabled and web_provider != "duckduckgo":
        required.add("WEB_SEARCH_API_KEY")
    return frozenset(required)


def plan_secrets(env: Mapping[str, str]) -> SecretPlan:
    values = select_secret_values(env)
    required = required_keys_for(env)
    missing = tuple(sorted(key for key in required if key not in values))
    present = tuple(sorted(values))
    optional_absent = tuple(
        sorted(
            key
            for key in SECRET_KEYS
            if key not in required and key not in values
        )
    )
    return SecretPlan(
        values=values,
        required=required,
        missing=missing,
        present=present,
        optional_absent=optional_absent,
    )


def validate_plan(plan: SecretPlan) -> None:
    if plan.missing:
        raise SecretsValidationError(plan.missing)


def build_opaque_secret(
    *,
    namespace: str,
    values: Mapping[str, str],
) -> dict:
    if not values:
        raise ValueError("secret values must not be empty")
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": SECRET_NAME,
            "namespace": namespace,
            "labels": dict(_PART_OF_LABELS),
        },
        "type": "Opaque",
        "stringData": dict(values),
    }


def render_yaml(manifest: Mapping) -> str:
    dumped = yaml.safe_dump(
        dict(manifest),
        sort_keys=False,
        allow_unicode=True,
    )
    return dumped if dumped.endswith("\n") else dumped + "\n"


def example_env_text() -> str:
    required_block = "\n".join(f"{key}=" for key in sorted(ALWAYS_REQUIRED))
    return (
        "# Vanessa K8s secrets catalog. Values live in the project .env — never "
        "commit them.\n"
        "# Apply with: poetry run python scripts/k8s_secrets.py apply\n"
        "# Do not kubectl-apply this file; it has no values.\n"
        "\n"
        "# --- always required ---\n"
        f"{required_block}\n"
        "\n"
        "# --- required when LLM_PROVIDER=deepseek (default) ---\n"
        "DEEPSEEK_API_KEY=\n"
        "\n"
        "# --- required when LLM_PROVIDER=claude ---\n"
        "ANTHROPIC_API_KEY=\n"
        "\n"
        "# --- required when WEB_SEARCH_ENABLED=true "
        "(unless provider=duckduckgo) ---\n"
        "WEB_SEARCH_API_KEY=\n"
        "\n"
        "# --- optional ---\n"
        "API_INTERNAL_TOKEN=\n"
        "HF_TOKEN=\n"
        "LANGFUSE_PUBLIC_KEY=\n"
        "LANGFUSE_SECRET_KEY=\n"
        "LANGFUSE_ID_SALT=\n"
    )
