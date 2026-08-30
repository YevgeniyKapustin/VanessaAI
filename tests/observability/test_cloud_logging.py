from pathlib import Path

import json
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


def test_logs_dashboard_is_portable_and_bounded() -> None:
    dashboard = json.loads(
        Path("grafana/dashboards/logs.json").read_text(encoding="utf-8"),
    )
    blob = json.dumps(dashboard)
    assert "${service:pipe}" in blob
    assert "${level:pipe}" in blob
    assert "${service:regex}" not in blob
    assert "${level:regex}" not in blob
    assert "${search:doublequote}" in blob
    assert "${query" not in blob
    assert "unwrap" not in blob
    assert dashboard["title"] == "Service Triage & Logs"
    assert dashboard["refresh"] == "30s"
    assert "30s" in dashboard["timepicker"]["refresh_intervals"]
    assert "1m" in dashboard["timepicker"]["refresh_intervals"]
    assert dashboard["templating"]["list"][0]["type"] == "datasource"
    names = [item["name"] for item in dashboard["templating"]["list"]]
    assert names == ["loki", "service", "level", "search"]
    search = dashboard["templating"]["list"][3]
    assert search["type"] == "textbox"
    assert search["current"]["value"] == ""
    assert search["query"] == ""
    level = dashboard["templating"]["list"][2]
    assert set(level["current"]["value"]) == {"info", "warn", "error", "fatal"}
    assert "debug" not in level["current"]["value"]
    assert level["allValue"] == ".+"
    assert dashboard["templating"]["list"][1]["allValue"] == ".+"

    def datasource_uids(panels: list) -> list[str]:
        found: list[str] = []
        for panel in panels:
            ds = panel.get("datasource") or {}
            if isinstance(ds, dict) and ds.get("uid"):
                found.append(str(ds["uid"]))
            for target in panel.get("targets") or []:
                tds = target.get("datasource") or {}
                if isinstance(tds, dict) and tds.get("uid"):
                    found.append(str(tds["uid"]))
            found.extend(datasource_uids(panel.get("panels") or []))
        return found

    assert set(datasource_uids(dashboard["panels"])) == {"${loki}"}
    by_id = {panel["id"]: panel for panel in dashboard["panels"]}
    assert by_id[2]["type"] == "text"
    assert by_id[10]["type"] == "row"
    assert by_id[10]["collapsed"] is False
    logs = by_id[3]
    assert logs["targets"][0]["maxLines"] == 200
    expr = logs["targets"][0]["expr"]
    assert '|= "${search:doublequote}"' in expr
    assert "| json | drop __error__" in expr
    assert "|~" not in expr
    knowledge = by_id[4]
    assert knowledge["title"] == "Knowledge node updates"
    assert knowledge["datasource"]["uid"] == "${loki}"
    assert knowledge["targets"][0]["datasource"]["uid"] == "${loki}"
    know_expr = knowledge["targets"][0]["expr"]
    assert "${service:pipe}" in know_expr
    assert "${level:pipe}" in know_expr
    assert 'event="knowledge_node_updated"' in know_expr
    assert "| json" not in know_expr
    logs_pos = logs["gridPos"]
    know_pos = knowledge["gridPos"]
    assert know_pos["y"] >= logs_pos["y"] + logs_pos["h"] + 1
    assert knowledge["targets"][0]["maxLines"] == 100


def test_nginx_latency_uses_prometheus_histogram() -> None:
    dashboard = json.loads(
        Path("grafana/dashboards/nginx.json").read_text(encoding="utf-8"),
    )
    blob = json.dumps(dashboard)
    assert "nginx_request_duration_seconds_bucket" in blob
    assert "histogram_quantile" in blob
    assert "unwrap" not in blob
    compose = Path("deploy/vector/vector.yaml").read_text(encoding="utf-8")
    cluster = Path("deploy/k8s/logging/vector.yaml").read_text(encoding="utf-8")
    for config in (compose, cluster):
        assert "type: log_to_metric" in config
        assert "type: prometheus_exporter" in config
        assert "level: \"{{ level }}\"" in config
        assert "event: \"{{ event }}\"" in config
    prometheus = Path("prometheus/prometheus.yml").read_text(encoding="utf-8")
    assert "vector:9598" in prometheus
    assert "api:8000" in prometheus
    assert "bot:9101" in prometheus
    assert "worker:9102" in prometheus
    assert "mcp-websearch:8101" in prometheus
    assert "mcp-knowledge:8102" in prometheus
    assert "mcp-vision:8103" in prometheus
    assert "host.docker.internal" not in prometheus
