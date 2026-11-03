"""Build every configured watch from its YAML plus settings.

A watch is enabled by an env flag, wired by env names declared in its YAML,
and parsed by the adapter of its ``kind``. A new notification of an already
supported kind is only a new YAML; a new payload shape adds one parser here.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from functools import partial
from pathlib import Path

from services.worker.announce.compose import AnnounceComposer
from services.worker.announce.content import WATCH_DIR, WatchSpec, load_watch
from services.worker.announce.mention import find_mention
from services.worker.announce.source import JsonSource
from services.worker.announce.watcher import Announcer, Parser
from services.worker.deploys.adapter import deploy_announcement
from services.worker.hermes.assembly import followup_model
from services.worker.hermes.prompt import build_followup_system_prompt
from vanessa.config.content import get_content, resolve_content_source
from vanessa.infrastructure.db.session import async_session_factory
from vanessa.llm.completers import create_chat_completer
from vanessa.pipeline.schedule.timing import schedule_zone

logger = logging.getLogger(__name__)

PARSERS: dict[str, Parser] = {"deploy": deploy_announcement}
_CHANNEL = "telegram"


def load_specs(directory: Path | None = None) -> list[WatchSpec]:
    folder = directory or resolve_content_source() / WATCH_DIR
    if not folder.is_dir():
        return []
    return [load_watch(path) for path in sorted(folder.glob("*.yaml"))]


def build_announcers(
    broker, settings, *, outbound_stream: str, directory: Path | None = None
) -> list[Announcer]:
    """Every enabled and fully configured watch; bad ones are skipped."""
    if broker is None or not outbound_stream:
        return []
    announcers = []
    for spec in load_specs(directory):
        announcer = _build(spec, broker, settings, outbound_stream)
        if announcer is not None:
            announcers.append(announcer)
    return announcers


def _build(spec: WatchSpec, broker, settings, outbound_stream: str) -> Announcer | None:
    if spec.enabled_env and not _value(settings, spec.enabled_env):
        return None
    parse = PARSERS.get(spec.kind)
    if parse is None:
        logger.warning("announce_unknown_kind watch=%s kind=%s", spec.id, spec.kind)
        return None
    missing = [
        name
        for name in (spec.url_env, spec.chat_id_env)
        if not _value(settings, name)
    ]
    if missing:
        logger.warning("announce_misconfigured watch=%s missing=%s", spec.id, ",".join(missing))
        return None
    links = {name: str(_value(settings, env) or "") for name, env in spec.link_envs.items()}
    return Announcer(
        spec,
        JsonSource(
            str(_value(settings, spec.url_env)),
            str(_value(settings, spec.token_env) or ""),
            path=spec.path,
        ),
        parse,
        _composer(spec, settings, links),
        broker,
        broker.announce_state(spec.state_key),
        outbound_stream=outbound_stream,
        chat_id=int(_value(settings, spec.chat_id_env)),
        probe_url=str(_value(settings, spec.probe_url_env) or ""),
        mention_finder=(
            partial(find_mention, async_session_factory) if spec.mention else None
        ),
    )


def _composer(spec: WatchSpec, settings, links: dict[str, str]) -> AnnounceComposer:
    content = get_content()
    generation = content.llm.generation.composer.to_params()
    if spec.max_tokens is not None:
        generation = replace(generation, max_tokens=spec.max_tokens)
    return AnnounceComposer(
        create_chat_completer(),
        model=followup_model(settings),
        system_prompt=build_followup_system_prompt(content, _CHANNEL),
        spec=spec,
        generation=generation,
        zone=schedule_zone(settings.schedule_timezone),
        links=links,
    )


def _value(settings, env_name: str):
    """``DEPLOY_CHAT_ID`` → the ``deploy_chat_id`` setting; None when absent."""
    if not env_name:
        return None
    return getattr(settings, env_name.lower(), None)


__all__ = ["PARSERS", "build_announcers", "load_specs"]
