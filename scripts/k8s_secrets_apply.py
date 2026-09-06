"""Apply-path helpers for ``scripts/k8s_secrets.py``."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from vanessa.k8s.configmap import (
    CONFIGMAP_NAME,
    build_configmap,
    select_config_values,
)
from vanessa.k8s.secrets import (
    SECRET_NAME,
    SecretPlan,
    render_yaml,
    rewrite_broker_host,
)


def print_key_list(title: str, keys) -> None:
    print(title)
    for key in keys:
        print(f"  - {key}")


def print_required(plan: SecretPlan) -> None:
    if plan.missing:
        print_key_list("required: MISSING", plan.missing)
        return
    print_key_list("required: OK", sorted(plan.required))


def print_plan(source: Path, namespace: str, plan: SecretPlan) -> None:
    print(f"source: {source}")
    print(f"namespace: {namespace}")
    print(f"secret: {SECRET_NAME}")
    print_required(plan)
    print_key_list(f"present ({len(plan.present)}):", plan.present)
    if plan.optional_absent:
        print_key_list("optional absent:", plan.optional_absent)


def rewrite_broker_if_needed(
    args: argparse.Namespace,
    env: dict[str, str],
    values: dict[str, str],
) -> None:
    if not args.broker_host:
        return
    redis_auth = env.get("REDIS_AUTH", "").strip() or None
    values["BROKER_REDIS_URL"] = rewrite_broker_host(
        values["BROKER_REDIS_URL"],
        args.broker_host,
        password=redis_auth,
    )
    print(f"broker host: {args.broker_host}")


def ensure_namespace_if_needed(
    args: argparse.Namespace,
    *,
    run_kubectl: Callable[..., None],
) -> None:
    if not args.ensure_namespace:
        return
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
    run_kubectl(args.kubectl, namespace_doc, dry_run=args.dry_run)


def apply_configmap_unless_skipped(
    args: argparse.Namespace,
    env: dict[str, str],
    *,
    run_kubectl: Callable[..., None],
) -> int:
    if args.skip_config:
        return 0
    config_values = select_config_values(
        env,
        postgres_host=args.postgres_host,
        qdrant_host=args.qdrant_host,
        langfuse_host=args.langfuse_host,
    )
    print(f"configmap: {CONFIGMAP_NAME} ({len(config_values)} keys)")
    manifest = build_configmap(namespace=args.namespace, values=config_values)
    run_kubectl(args.kubectl, render_yaml(manifest), dry_run=args.dry_run)
    print(f"applied {len(config_values)} keys to ConfigMap/{CONFIGMAP_NAME}")
    return 0
