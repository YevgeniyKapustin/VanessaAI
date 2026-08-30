from pathlib import Path

import pytest
import yaml

from vanessa.k8s.configmap import (
    CLUSTER_OVERRIDES,
    CONFIGMAP_NAME,
    build_configmap,
    select_config_values,
)
from vanessa.k8s.secrets import (
    ALWAYS_REQUIRED,
    SECRET_KEYS,
    SECRET_NAME,
    SecretsValidationError,
    build_opaque_secret,
    example_env_text,
    load_env_file,
    plan_secrets,
    render_yaml,
    required_keys_for,
    rewrite_broker_host,
    select_secret_values,
    validate_plan,
)


def test_rewrite_broker_host_keeps_password_and_db():
    url = "redis://:s3cret@redis:6379/1"
    rewritten = rewrite_broker_host(url, "host.docker.internal")
    assert rewritten == "redis://:s3cret@host.docker.internal:6379/1"
    assert "redis:" not in rewritten.split("@", 1)[1]


def test_rewrite_broker_host_without_auth():
    url = "redis://localhost:6379/1"
    rewritten = rewrite_broker_host(url, "host.docker.internal")
    assert rewritten == "redis://host.docker.internal:6379/1"


def test_rewrite_broker_host_overrides_password():
    url = "redis://:stale@redis:6379/0"
    rewritten = rewrite_broker_host(
        url, "host.docker.internal", password="s3cret"
    )
    assert rewritten == "redis://:s3cret@host.docker.internal:6379/0"


def test_fill_broker_url_from_redis_auth():
    from vanessa.k8s.secrets import fill_broker_url

    filled = fill_broker_url({"REDIS_AUTH": "s3cret"})
    assert filled["BROKER_REDIS_URL"] == "redis://:s3cret@redis:6379/0"
    existing = fill_broker_url(
        {
            "REDIS_AUTH": "s3cret",
            "BROKER_REDIS_URL": "redis://:other@redis:6379/1",
        }
    )
    assert existing["BROKER_REDIS_URL"] == "redis://:other@redis:6379/1"

_MINIMAL_ENV = {
    "TELEGRAM_BOT_TOKEN": "tg-token",
    "POSTGRES_PASSWORD": "pg-pass",
    "BROKER_REDIS_URL": "redis://:pass@redis:6379/1",
    "DEEPSEEK_API_KEY": "ds-key",
}


def test_select_config_values_keeps_owner_id_and_drops_secrets():
    env = {
        **_MINIMAL_ENV,
        "REQUIRED_USER_TELEGRAM_ID": "123456789",
        "ALLOWED_CHAT_TELEGRAM_ID": "-1001111111111",
        "REDIS_AUTH": "compose-only",
        "LANGFUSE_REDIS_AUTH": "langfuse-only",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE_ENABLED": "true",
        "POSTGRES_HOST": "postgres",
    }
    selected = select_config_values(
        env,
        postgres_host="host.docker.internal",
        qdrant_host="host.docker.internal",
        langfuse_host="http://host.docker.internal:3000",
    )
    assert selected["REQUIRED_USER_TELEGRAM_ID"] == "123456789"
    assert selected["ALLOWED_CHAT_TELEGRAM_ID"] == "-1001111111111"
    assert selected["POSTGRES_HOST"] == "host.docker.internal"
    assert selected["QDRANT_HOST"] == "host.docker.internal"
    assert selected["LANGFUSE_HOST"] == "http://host.docker.internal:3000"
    assert selected["TRANSPORT"] == CLUSTER_OVERRIDES["TRANSPORT"]
    assert selected["LOG_JSON"] == "true"
    assert selected["LOG_FILE_ENABLED"] == "false"
    assert selected["MCP_FAIL_OPEN"] == "false"
    assert selected["KNOWLEDGE_STORE"] == "postgres"
    assert "TELEGRAM_BOT_TOKEN" not in selected
    assert "REDIS_AUTH" not in selected
    assert "LANGFUSE_REDIS_AUTH" not in selected
    manifest = build_configmap(namespace="vanessa", values=selected)
    assert manifest["metadata"]["name"] == CONFIGMAP_NAME
    assert "TELEGRAM_BOT_TOKEN" not in manifest["data"]


def test_select_secret_values_ignores_non_secret_keys():
    env = {
        **_MINIMAL_ENV,
        "LOG_LEVEL": "DEBUG",
        "POSTGRES_HOST": "postgres",
        "HF_TOKEN": "hf-token",
    }
    selected = select_secret_values(env)
    assert "LOG_LEVEL" not in selected
    assert "POSTGRES_HOST" not in selected
    assert selected["HF_TOKEN"] == "hf-token"
    assert selected["TELEGRAM_BOT_TOKEN"] == "tg-token"


def test_select_secret_values_skips_empty():
    env = {**_MINIMAL_ENV, "HF_TOKEN": "  ", "API_INTERNAL_TOKEN": ""}
    selected = select_secret_values(env)
    assert "HF_TOKEN" not in selected
    assert "API_INTERNAL_TOKEN" not in selected


def test_load_env_file_strips_and_drops_empty(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "TELEGRAM_BOT_TOKEN= abc \n"
        "POSTGRES_PASSWORD=\n"
        "LOG_LEVEL=INFO\n"
        "# comment\n",
        encoding="utf-8",
    )
    loaded = load_env_file(path)
    assert loaded["TELEGRAM_BOT_TOKEN"] == "abc"
    assert "POSTGRES_PASSWORD" not in loaded
    assert loaded["LOG_LEVEL"] == "INFO"


def test_required_keys_default_deepseek():
    required = required_keys_for({})
    assert required == ALWAYS_REQUIRED | {"DEEPSEEK_API_KEY"}
    assert "ANTHROPIC_API_KEY" not in required


def test_required_keys_claude():
    required = required_keys_for({"LLM_PROVIDER": "claude"})
    assert "ANTHROPIC_API_KEY" in required
    assert "DEEPSEEK_API_KEY" not in required


def test_required_keys_web_search():
    required = required_keys_for(
        {
            "WEB_SEARCH_ENABLED": "true",
            "WEB_SEARCH_PROVIDER": "tavily",
        }
    )
    assert "WEB_SEARCH_API_KEY" in required
    duck = required_keys_for(
        {
            "WEB_SEARCH_ENABLED": "true",
            "WEB_SEARCH_PROVIDER": "duckduckgo",
        }
    )
    assert "WEB_SEARCH_API_KEY" not in duck


def test_plan_reports_missing_required():
    plan = plan_secrets({"TELEGRAM_BOT_TOKEN": "tg-token"})
    assert "POSTGRES_PASSWORD" in plan.missing
    assert "DEEPSEEK_API_KEY" in plan.missing
    with pytest.raises(SecretsValidationError) as exc:
        validate_plan(plan)
    assert "POSTGRES_PASSWORD" in exc.value.missing


def test_plan_ok_minimal():
    plan = plan_secrets(_MINIMAL_ENV)
    validate_plan(plan)
    assert plan.missing == ()
    assert set(plan.present) == set(_MINIMAL_ENV)
    assert "HF_TOKEN" in plan.optional_absent


def test_build_opaque_secret_yaml_roundtrip():
    manifest = build_opaque_secret(
        namespace="vanessa",
        values=_MINIMAL_ENV,
    )
    assert manifest["metadata"]["name"] == SECRET_NAME
    assert manifest["stringData"] == _MINIMAL_ENV
    dumped = render_yaml(manifest)
    loaded = yaml.safe_load(dumped)
    assert loaded["kind"] == "Secret"
    assert loaded["stringData"]["TELEGRAM_BOT_TOKEN"] == "tg-token"
    assert "LOG_LEVEL" not in loaded["stringData"]


def test_build_opaque_secret_rejects_empty():
    with pytest.raises(ValueError):
        build_opaque_secret(namespace="vanessa", values={})


def test_example_env_matches_committed_file():
    committed = Path("deploy/k8s/secrets.env.example").read_text(encoding="utf-8")
    assert committed == example_env_text()
    for key in SECRET_KEYS:
        assert f"{key}=" in committed


def test_kustomization_does_not_include_secrets():
    text = Path("deploy/k8s/kustomization.yaml").read_text(encoding="utf-8")
    base = Path("deploy/k8s/base/kustomization.yaml").read_text(encoding="utf-8")
    assert "11-secrets" not in text
    assert "secrets.env" not in text
    assert "30-networkpolicy" not in text
    assert "10-configmap.yaml" not in base
    assert "40-pvc.yaml" not in base
    assert not Path("deploy/k8s/11-secrets.yaml").exists()
    assert not Path("deploy/k8s/base/40-pvc.yaml").exists()


def test_workloads_pin_local_image_and_secretref():
    from vanessa.k8s.secrets import IMAGE

    for name in (
        "20-agent-core.yaml",
        "21-bot.yaml",
        "22-worker.yaml",
        "23-mcp-servers.yaml",
    ):
        raw = Path("deploy/k8s/base") / name
        text = raw.read_text(encoding="utf-8")
        assert IMAGE in text
        assert "imagePullPolicy: IfNotPresent" in text
        assert "vanessa-agent:latest" not in text
        assert "name: vanessa-secrets" in text
        assert "secretRef:" not in text
        assert "automountServiceAccountToken: false" in text
        assert "readOnlyRootFilesystem: true" in text
    agent = Path("deploy/k8s/base/20-agent-core.yaml").read_text(encoding="utf-8")
    assert "containerPort: 9100" not in agent
    assert "vanessa.db.locked_upgrade" in agent
    bot = Path("deploy/k8s/base/21-bot.yaml").read_text(encoding="utf-8")
    assert "replicas: 1" in bot
    assert "path: /health" in bot
