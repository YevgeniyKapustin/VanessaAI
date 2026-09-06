#!/usr/bin/env python
"""Single entry point for Vanessa Kubernetes secrets.

Reads `.env.defaults` plus a host overlay (default: `.env.local`), keeps only the
secret-key catalog, validates required keys, and applies Secret `vanessa-secrets`
plus ConfigMap `vanessa-config` (unless `--skip-config`).

    poetry run python scripts/k8s_secrets.py check
    poetry run python scripts/k8s_secrets.py apply
    poetry run python scripts/k8s_secrets.py apply --dry-run
    poetry run python scripts/k8s_secrets.py example
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.k8s_secrets_apply import (
    apply_configmap_unless_skipped,
    ensure_namespace_if_needed,
    print_plan,
    rewrite_broker_if_needed,
)
from scripts.k8s_secrets_cli import _run_kubectl, build_parser
from vanessa.k8s.configmap import (
    CONFIGMAP_NAME,
    build_configmap,
    select_config_values,
)
from vanessa.k8s.secrets import (
    SECRET_NAME,
    SecretPlan,
    SecretsValidationError,
    build_opaque_secret,
    example_env_text,
    fill_broker_url,
    load_env_file,
    plan_secrets,
    render_yaml,
    validate_plan,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


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


def cmd_check(args: argparse.Namespace) -> int:
    _, plan = _load_plan(args.from_env)
    print_plan(args.from_env, args.namespace, plan)
    if plan.missing:
        return 2
    return 0


def cmd_example(_: argparse.Namespace) -> int:
    text = example_env_text()
    sys.stdout.write(text)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    env, plan = _load_plan(args.from_env)
    print_plan(args.from_env, args.namespace, plan)
    try:
        validate_plan(plan)
    except SecretsValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    values = dict(plan.values)
    rewrite_broker_if_needed(args, env, values)
    ensure_namespace_if_needed(args, run_kubectl=_run_kubectl)
    secret = build_opaque_secret(namespace=args.namespace, values=values)
    _run_kubectl(args.kubectl, render_yaml(secret), dry_run=args.dry_run)
    print(f"applied {len(plan.values)} keys to Secret/{SECRET_NAME}")
    return apply_configmap_unless_skipped(
        args, env, run_kubectl=_run_kubectl
    )


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


_COMMANDS = {
    "check": cmd_check,
    "example": cmd_example,
    "apply": cmd_apply,
    "apply-config": cmd_apply_config,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
