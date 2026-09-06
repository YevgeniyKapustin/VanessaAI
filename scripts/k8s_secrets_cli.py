"""CLI parser and kubectl apply helper for ``scripts/k8s_secrets.py``."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from vanessa.k8s.configmap import CONFIGMAP_NAME
from vanessa.k8s.secrets import DEFAULT_NAMESPACE

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply Vanessa K8s secrets from .env.defaults + .env.local. "
            "This is the only supported way to put secrets into the cluster."
        ),
    )
    parser.add_argument(
        "--from-env",
        type=Path,
        default=_PROJECT_ROOT / ".env.local",
        help="Env file to read (default: project .env.local)",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Kubernetes namespace (default: {DEFAULT_NAMESPACE})",
    )
    parser.add_argument(
        "--kubectl",
        default="kubectl",
        help="kubectl binary (default: kubectl from PATH)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Validate required keys; print names only")
    sub.add_parser("example", help="Print the committed secrets catalog")

    apply = sub.add_parser(
        "apply",
        help="kubectl apply Secret and ConfigMap",
    )
    apply.add_argument(
        "--dry-run",
        action="store_true",
        help="kubectl --dry-run=client; does not persist to the cluster",
    )
    apply.add_argument(
        "--ensure-namespace",
        action="store_true",
        help="Create the namespace if it does not exist",
    )
    apply.add_argument(
        "--broker-host",
        default=None,
        help="Rewrite BROKER_REDIS_URL hostname (hybrid Docker Desktop)",
    )
    apply.add_argument(
        "--skip-config",
        action="store_true",
        help="Apply Secret only (default also applies ConfigMap)",
    )
    apply.add_argument(
        "--postgres-host",
        default=None,
        help="Override POSTGRES_HOST in the generated ConfigMap",
    )
    apply.add_argument(
        "--qdrant-host",
        default=None,
        help="Override QDRANT_HOST in the generated ConfigMap",
    )
    apply.add_argument(
        "--langfuse-host",
        default=None,
        help="Override LANGFUSE_HOST in the generated ConfigMap",
    )

    cfg = sub.add_parser(
        "apply-config",
        help=f"kubectl apply ConfigMap/{CONFIGMAP_NAME} from .env (non-secrets)",
    )
    cfg.add_argument(
        "--dry-run",
        action="store_true",
        help="kubectl --dry-run=client; does not persist to the cluster",
    )
    cfg.add_argument(
        "--postgres-host",
        default=None,
        help="Override POSTGRES_HOST (e.g. host.docker.internal)",
    )
    cfg.add_argument(
        "--qdrant-host",
        default=None,
        help="Override QDRANT_HOST (e.g. host.docker.internal)",
    )
    cfg.add_argument(
        "--langfuse-host",
        default=None,
        help="Override LANGFUSE_HOST (e.g. http://host.docker.internal:3000)",
    )
    return parser


def _kubectl_cmd(kubectl: str, *, dry_run: bool) -> list[str]:
    cmd = [kubectl, "apply", "-f", "-"]
    if dry_run:
        cmd.append("--dry-run=client")
    return cmd


def _process_error_detail(exc: subprocess.CalledProcessError) -> str:
    if exc.stderr:
        return exc.stderr.strip()
    if exc.stdout:
        return exc.stdout.strip()
    return str(exc).strip()


def _print_kubectl_stdout(completed: subprocess.CompletedProcess[str]) -> None:
    stdout = completed.stdout.strip()
    if stdout:
        print(stdout)


def _run_kubectl(
    kubectl: str,
    document: str,
    *,
    dry_run: bool,
) -> None:
    cmd = _kubectl_cmd(kubectl, dry_run=dry_run)
    try:
        completed = subprocess.run(
            cmd,
            input=document,
            text=True,
            encoding="utf-8",
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            f"kubectl not found ({kubectl}). Install Docker Desktop Kubernetes "
            f"or put kubectl on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = _process_error_detail(exc)
        raise SystemExit(f"kubectl apply failed: {detail}") from exc
    _print_kubectl_stdout(completed)
