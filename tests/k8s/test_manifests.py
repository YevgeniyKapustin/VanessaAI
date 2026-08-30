from pathlib import Path

import yaml

from vanessa.k8s.secrets import IMAGE, WORKLOAD_SECRET_KEYS


def _docs(path: Path) -> list[dict]:
    return [
        doc
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if doc
    ]


def _secret_keys(container: dict) -> set[str]:
    keys: set[str] = set()
    for item in container.get("env") or []:
        ref = (item.get("valueFrom") or {}).get("secretKeyRef") or {}
        key = ref.get("key")
        if key:
            keys.add(str(key))
    return keys


def _container(doc: dict, name: str) -> dict:
    containers = doc["spec"]["template"]["spec"].get("containers") or []
    for container in containers:
        if container["name"] == name:
            return container
    raise AssertionError(f"container {name} not found in {doc['metadata']}")


def _init_container(doc: dict, name: str) -> dict:
    containers = doc["spec"]["template"]["spec"].get("initContainers") or []
    for container in containers:
        if container["name"] == name:
            return container
    raise AssertionError(f"init {name} not found in {doc['metadata']}")


def test_workload_secret_keys_match_catalog() -> None:
    agent = next(
        doc
        for doc in _docs(Path("deploy/k8s/base/20-agent.yaml"))
        if doc.get("kind") == "Deployment"
    )
    bot = next(
        doc
        for doc in _docs(Path("deploy/k8s/base/21-bot.yaml"))
        if doc.get("kind") == "Deployment"
    )
    worker = next(
        doc
        for doc in _docs(Path("deploy/k8s/base/22-worker.yaml"))
        if doc.get("kind") == "Deployment"
    )
    mcps = [
        doc
        for doc in _docs(Path("deploy/k8s/base/23-mcp-servers.yaml"))
        if doc.get("kind") == "Deployment"
    ]
    by_name = {doc["metadata"]["name"]: doc for doc in mcps}
    assert _secret_keys(_container(agent, "agent")) == WORKLOAD_SECRET_KEYS[
        "agent"
    ]
    assert _secret_keys(_init_container(agent, "migrate")) == (
        WORKLOAD_SECRET_KEYS["migrate"]
    )
    assert _secret_keys(_container(bot, "bot")) == WORKLOAD_SECRET_KEYS["bot"]
    assert _secret_keys(_container(worker, "worker")) == WORKLOAD_SECRET_KEYS[
        "worker"
    ]
    assert _secret_keys(_init_container(worker, "migrate")) == (
        WORKLOAD_SECRET_KEYS["migrate"]
    )
    assert _secret_keys(_container(by_name["mcp-websearch"], "server")) == (
        WORKLOAD_SECRET_KEYS["mcp-websearch"]
    )
    assert _secret_keys(_container(by_name["mcp-knowledge"], "server")) == (
        WORKLOAD_SECRET_KEYS["mcp-knowledge"]
    )
    assert _secret_keys(_container(by_name["mcp-vision"], "server")) == (
        WORKLOAD_SECRET_KEYS["mcp-vision"]
    )


def test_loki_is_statefulset_with_retention() -> None:
    docs = _docs(Path("deploy/k8s/logging/20-loki.yaml"))
    kinds = {doc["kind"] for doc in docs}
    assert "StatefulSet" in kinds
    assert "Deployment" not in kinds
    cluster = yaml.safe_load(
        Path("deploy/k8s/logging/loki-config.yaml").read_text(encoding="utf-8")
    )
    assert cluster["compactor"]["retention_enabled"] is True
    assert cluster["limits_config"]["retention_period"] == "168h"


def test_desktop_overlay_does_not_patch_configmap() -> None:
    text = Path("deploy/k8s/overlays/desktop/kustomization.yaml").read_text(
        encoding="utf-8",
    )
    assert "configmap-hosts" not in text
    assert "delete-pvc" not in text
    assert "namespace-pss" not in text
    assert "kind: StatefulSet" in text
    assert IMAGE not in text
    loki_patch = Path(
        "deploy/k8s/overlays/desktop/loki-hostport.yaml"
    ).read_text(encoding="utf-8")
    assert "kind: StatefulSet" in loki_patch
    assert not Path(
        "deploy/k8s/overlays/desktop/namespace-pss.yaml"
    ).exists()


def test_workloads_use_readonly_rootfs() -> None:
    for name in (
        "20-agent.yaml",
        "21-bot.yaml",
        "22-worker.yaml",
        "23-mcp-servers.yaml",
    ):
        for doc in _docs(Path("deploy/k8s/base") / name):
            if doc.get("kind") != "Deployment":
                continue
            spec = doc["spec"]["template"]["spec"]
            volumes = spec.get("volumes") or []
            assert any(item.get("name") == "tmp" for item in volumes)
            for container in spec.get("containers") or []:
                ctx = container.get("securityContext") or {}
                assert ctx.get("readOnlyRootFilesystem") is True
                mounts = container.get("volumeMounts") or []
                assert any(item.get("mountPath") == "/tmp" for item in mounts)
            for container in spec.get("initContainers") or []:
                ctx = container.get("securityContext") or {}
                assert ctx.get("readOnlyRootFilesystem") is True


def test_postgres_networkpolicy_allows_mcp_knowledge() -> None:
    docs = _docs(Path("deploy/k8s/base/30-networkpolicy.yaml"))
    postgres = next(
        doc for doc in docs if doc["metadata"]["name"] == "allow-to-postgres"
    )
    expr = postgres["spec"]["ingress"][0]["from"][0]["podSelector"][
        "matchExpressions"
    ][0]
    assert "mcp-knowledge" in expr["values"]
    assert "agent" in expr["values"]
    assert "worker" in expr["values"]
