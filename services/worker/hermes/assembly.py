"""Build the ``hermes_ask`` handler (None when Hermes is off)."""

from __future__ import annotations

from dataclasses import replace

from services.worker.hermes.compose import FollowupComposer
from services.worker.hermes.handler import HermesAskHandler
from services.worker.hermes.payload import SUPPORTED_CHANNEL
from services.worker.hermes.prompt import build_followup_system_prompt
from services.worker.hermes.runner import HermesRunner
from vanessa.config.content import AppContent, get_content
from vanessa.config.content_hermes import (
    HermesContent,
    get_hermes_content,
    get_report_css,
)
from vanessa.infrastructure.hermes import HermesClient, create_hermes_client
from vanessa.llm.completers import create_chat_completer


def followup_model(settings) -> str:
    """Same model choice as the other worker LLM calls (memory, metrics)."""
    return settings.knowledge_model or settings.planner_model


def build_followup_composer(
    settings, content: AppContent, prompts: HermesContent
) -> FollowupComposer:
    generation = replace(
        content.llm.generation.composer.to_params(), max_tokens=prompts.max_tokens
    )
    return FollowupComposer(
        create_chat_completer(),
        model=followup_model(settings),
        system_prompt=build_followup_system_prompt(content, SUPPORTED_CHANNEL),
        prompts=prompts,
        generation=generation,
    )


def build_hermes_runner(
    client: HermesClient, broker, *, outbound_stream: str, settings
) -> HermesRunner:
    prompts = get_hermes_content()
    return HermesRunner(
        client,
        build_followup_composer(settings, get_content(), prompts),
        broker,
        outbound_stream=outbound_stream,
        instructions=prompts.run_instructions,
        poll_seconds=settings.hermes_poll_seconds,
        max_wait_seconds=settings.hermes_max_wait_seconds,
        file_max_bytes=settings.hermes_file_max_bytes,
        report_css=get_report_css(),
    )


def build_hermes_handler(
    broker, *, outbound_stream: str, settings
) -> HermesAskHandler | None:
    """The handler, or None when Hermes is off or there is nowhere to post."""
    client = create_hermes_client(settings)
    if client is None or broker is None or not outbound_stream:
        return None
    runner = build_hermes_runner(
        client, broker, outbound_stream=outbound_stream, settings=settings
    )
    return HermesAskHandler(runner, max_parallel=settings.hermes_max_parallel)
