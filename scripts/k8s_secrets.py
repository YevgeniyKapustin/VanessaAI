#!/usr/bin/env python
"""Single entry point for Vanessa Kubernetes secrets.

Reads `.env.defaults` plus a host overlay (default: `.env.local`), keeps only the
secret-key catalog, validates required keys, and applies one Opaque Secret
(`vanessa-secrets`).

    poetry run python scripts/k8s_secrets.py check
    poetry run python scripts/k8s_secrets.py apply
    poetry run python scripts/k8s_secrets.py apply --dry-run
    poetry run python scripts/k8s_secrets.py example
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from vanessa.k8s.configmap import (
    CONFIGMAP_NAME,
    build_configmap,
    select_config_values,
)
from vanessa.k8s.secrets import (
    DEFAULT_NAMESPACE,
    SECRET_NAME,
    SecretPlan,
    SecretsValidationError,
    build_opaque_secret,
    example_env_text,
    fill_broker_url,
    load_env_file,
    plan_secrets,
    render_yaml,
    rewrite_broker_host,
    validate_plan,
)


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
        help=f"kubectl apply Secret/{SECRET_NAME}",
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


def _print_plan(source: Path, namespace: str, plan: SecretPlan) -> None:
    print(f"source: {source}")
    print(f"namespace: {namespace}")
    print(f"secret: {SECRET_NAME}")
    if plan.missing:
        print("required: MISSING")
        for key in plan.missing:
            print(f"  - {key}")
    else:
        print("required: OK")
        for key in sorted(plan.required):
            print(f"  - {key}")
    print(f"present ({len(plan.present)}):")
    for key in plan.present:
        print(f"  - {key}")
    if plan.optional_absent:
        print("optional absent:")
        for key in plan.optional_absent:
            print(f"  - {key}")


def _load_plan(env_path: Path) -> tuple[dict[str, str], SecretPlan]:
    if not env_path.is_file():
        raise SystemExit(f"env file not found: {env_path}")
    env: dict[str, str] = {}
    defaults_path = env_path.parent / ".env.defaults"
    if defaults_path.is_file() and env_path.resolve() != defaults_path.resolve():
        env.update(load_env_file(defaults_path))
    env.update(load_env_file(env_path))
    env = fill_broker_url(env)
    return env, plan_secrets(env)


def _run_kubectl(
    kubectl: str,
    document: str,
    *,
    dry_run: bool,
) -> None:
    cmd = [kubectl, "apply", "-f", "-"]
    if dry_run:
        cmd.append("--dry-run=client")
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
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise SystemExit(f"kubectl apply failed: {detail}") from exc
    stdout = completed.stdout.strip()
    if stdout:
        print(stdout)


def cmd_check(args: argparse.Namespace) -> int:
    _, plan = _load_plan(args.from_env)
    _print_plan(args.from_env, args.namespace, plan)
    if plan.missing:
        return 2
    return 0


def cmd_example(_: argparse.Namespace) -> int:
    text = example_env_text()
    sys.stdout.write(text)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    env, plan = _load_plan(args.from_env)
    _print_plan(args.from_env, args.namespace, plan)
    try:
        validate_plan(plan)
    except SecretsValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    values = dict(plan.values)
    if args.broker_host:
        redis_auth = env.get("REDIS_AUTH", "").strip() or None
        values["BROKER_REDIS_URL"] = rewrite_broker_host(
            values["BROKER_REDIS_URL"],
            args.broker_host,
            password=redis_auth,
        )
        print(f"broker host: {args.broker_host}")
    if args.ensure_namespace:
        namespace_doc = render_yaml(
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {
                    "name": args.namespace,
                    "labels": {
                        "vanessa.kubernetes.io/part-of": "vanessa",
                    },
                },
            }
        )
        _run_kubectl(args.kubectl, namespace_doc, dry_run=args.dry_run)
    secret = build_opaque_secret(namespace=args.namespace, values=values)
    _run_kubectl(args.kubectl, render_yaml(secret), dry_run=args.dry_run)
    print(f"applied {len(plan.values)} keys to Secret/{SECRET_NAME}")
    return 0


def cmd_apply_config(args: argparse.Namespace) -> int:
    env, _plan = _load_plan(args.from_env)
    values = select_config_values(
        env,
        postgres_host=args.postgres_host,
        qdrant_host=args.qdrant_host,
        langfuse_host=args.langfuse_host,
    )
    print(f"source: {args.from_env}")
    print(f"namespace: {args.namespace}")
    print(f"configmap: {CONFIGMAP_NAME} ({len(values)} keys)")
    for key in values:
        print(f"  - {key}")
    manifest = build_configmap(namespace=args.namespace, values=values)
    _run_kubectl(args.kubectl, render_yaml(manifest), dry_run=args.dry_run)
    print(f"applied {len(values)} keys to ConfigMap/{CONFIGMAP_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "example":
        return cmd_example(args)
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "apply-config":
        return cmd_apply_config(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
