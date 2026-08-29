from pathlib import Path

import yaml


def test_nginx_writes_json_to_stdout() -> None:
    text = Path("deploy/nginx/nginx.conf").read_text(encoding="utf-8")
    assert "error_log /dev/stderr warn;" in text
    assert "access_log /dev/stdout json;" in text
    assert "log_format json escape=json" in text
    assert '"request_time":$request_time' in text
    assert '"status":$status' in text
    assert '"upstream_response_time":"$upstream_response_time"' in text
    assert "/var/log/nginx" not in text


def test_k8s_configmap_disables_container_files() -> None:
    text = Path("deploy/k8s/base/10-configmap.yaml").read_text(encoding="utf-8")
    assert 'LOG_JSON: "true"' in text
    assert 'LOG_FILE_ENABLED: "false"' in text


def test_vector_daemonset_tails_pod_logs() -> None:
    manifest = Path("deploy/k8s/logging/21-vector.yaml").read_text(
        encoding="utf-8",
    )
    assert "kind: DaemonSet" in manifest
    assert "path: /var/log" in manifest
    config = Path("deploy/k8s/logging/vector.yaml").read_text(encoding="utf-8")
    assert "type: kubernetes_logs" in config
    assert "extra_label_selector: app=vanessa" in config
    assert "type: loki" in config
    assert "endpoint: http://loki.logging.svc.cluster.local:3100" in config


def test_compose_vector_ships_docker_logs_to_loki() -> None:
    config = Path("deploy/vector/vector.yaml").read_text(encoding="utf-8")
    assert "type: docker_logs" in config
    assert "endpoint: http://loki:3100" in config
    compose = Path("docker-compose.monitoring.yml").read_text(encoding="utf-8")
    assert "grafana/loki:" in compose
    assert "timberio/vector:" in compose


def test_loki_schema_is_tsdb_v13() -> None:
    compose = Path("deploy/loki/loki-config.yaml").read_text(encoding="utf-8")
    cluster = Path("deploy/k8s/logging/loki-config.yaml").read_text(
        encoding="utf-8",
    )
    config = yaml.safe_load(compose)
    period = config["schema_config"]["configs"][0]
    assert period["store"] == "tsdb"
    assert period["schema"] == "v13"
    assert period["object_store"] == "filesystem"
    assert yaml.safe_load(cluster)["schema_config"] == config["schema_config"]
    assert yaml.safe_load(cluster)["common"] == config["common"]


def test_kustomizations_include_logging_stack() -> None:
    root = Path("deploy/k8s/kustomization.yaml").read_text(encoding="utf-8")
    desktop = Path("deploy/k8s/overlays/desktop/kustomization.yaml").read_text(
        encoding="utf-8",
    )
    assert "- logging" in root
    assert "- ../../logging" in desktop


def test_grafana_has_loki_datasource() -> None:
    text = Path("grafana/provisioning/datasources/loki.yml").read_text(
        encoding="utf-8",
    )
    assert "uid: loki" in text
    assert "url: http://loki:3100" in text
    dashboard = Path("grafana/dashboards/logs.json").read_text(encoding="utf-8")
    assert '"uid": "vanessa-logs"' in dashboard
    assert '"uid": "loki"' in dashboard
