from __future__ import annotations

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
