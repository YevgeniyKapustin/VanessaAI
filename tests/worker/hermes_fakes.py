"""Fakes for the worker Hermes tests (no network)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from services.worker.hermes.compose import FollowupComposer
from services.worker.hermes.payload import HermesAsk
from services.worker.hermes.runner import HermesRunner
from vanessa.config.content_hermes import get_hermes_content
from vanessa.contracts.messages import TaskKind, TaskMessage
from vanessa.infrastructure.hermes import HermesRun, HermesUnavailableError
from vanessa.llm.generation import LLMGenerationParams

CHAT_ID = -100123
MESSAGE_ID = 42
SYSTEM = "SYSTEM PERSONA"


def ask_task(**payload_overrides) -> TaskMessage:
    payload = {
        "question": "что в Plane по VAN-12?",
        "channel": "telegram",
        "telegram_chat_id": CHAT_ID,
        "telegram_message_id": MESSAGE_ID,
        "user_message": "Ванесса, спроси гермеса про VAN-12",
    }
    payload.update(payload_overrides)
    return TaskMessage(
        task=TaskKind.HERMES_ASK,
        payload=payload,
        dedup_key=f"hermes:{CHAT_ID}:{MESSAGE_ID}",
    )


def make_ask(**overrides) -> HermesAsk:
    base = HermesAsk(
        question="что в Plane по VAN-12?",
        channel="telegram",
        telegram_chat_id=CHAT_ID,
        telegram_message_id=MESSAGE_ID,
        user_message="спроси гермеса",
        idempotency_key=f"hermes:{CHAT_ID}:{MESSAGE_ID}",
    )
    return replace(base, **overrides)


class FakeClient:
    def __init__(self, *, status: str = "completed", output: str = "", fail: bool = False):
        self.status = status
        self.output = output
        self.fail = fail
        self.started: list[tuple[str, dict]] = []
        self.stopped: list[str] = []

    async def start_run(self, question: str, **kwargs) -> str:
        if self.fail:
            raise HermesUnavailableError("hermes unreachable: http://secret-tunnel")
        self.started.append((question, kwargs))
        return "run-1"

    async def get_run(self, run_id: str) -> HermesRun:
        return HermesRun(run_id=run_id, status=self.status, output=self.output)

    async def stop_run(self, run_id: str) -> None:
        self.stopped.append(run_id)


class FakeCompleter:
    def __init__(self, reply: str = "", *, error: Exception | None = None, provider="deepseek"):
        self.reply = reply
        self.error = error
        self.provider = provider
        self.calls: list[dict] = []

    async def complete(self, model, messages, *, kind="completion", **kwargs) -> str:
        self.calls.append({"model": model, "messages": messages, "kind": kind, **kwargs})
        if self.error is not None:
            raise self.error
        return self.reply


class FakeBroker:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.published: list[tuple[str, object]] = []
        self.error = error

    async def publish(self, stream: str, message) -> str:
        if self.error is not None:
            raise self.error
        self.published.append((stream, message))
        return "1-0"


class BlockingRunner:
    """Runner that waits on an event; counts concurrent runs."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.started: list[HermesAsk] = []
        self.cancelled = 0
        self.active = 0
        self.peak = 0

    async def run(self, ask: HermesAsk) -> None:
        self.started.append(ask)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1


def make_composer(completer: FakeCompleter) -> FollowupComposer:
    return FollowupComposer(
        completer,
        model="test-model",
        system_prompt=SYSTEM,
        prompts=get_hermes_content(),
        generation=LLMGenerationParams(temperature=0.5, top_p=0.9, max_tokens=900),
    )


def make_runner(client: FakeClient, completer: FakeCompleter, broker: FakeBroker):
    return HermesRunner(
        client,
        make_composer(completer),
        broker,
        outbound_stream="vanessa:outbound",
        instructions="work only",
        poll_seconds=0.0,
        max_wait_seconds=60.0,
    )
