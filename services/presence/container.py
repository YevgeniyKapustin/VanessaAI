from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from services.presence.avatar import AvatarConfig, load_avatar
from services.presence.broker import PresenceBroker
from services.presence.capture import default_grab
from services.presence.capture.scale import default_encode
from services.presence.ingress import parse_ingress_line, turn_from_osc
from services.presence.loop import run_queue
from services.presence.models import PresenceTurn
from services.presence.osc.client import OscSender, build_sender
from services.presence.osc.listener import start_osc_listener
from services.presence.playback.audio import AudioPlayer, DefaultPlayer
from services.presence.playback.idle import idle_loop
from services.presence.playback.speech import load_synthesizer
from vanessa.config import settings
from vanessa.core import SpeechSynthesizer
from vanessa.infrastructure.broker.redis_streams import RedisStreamBroker
from vanessa.infrastructure.broker.streams import BrokerStreams

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PresenceServices:
    avatar: AvatarConfig
    osc: OscSender
    broker: PresenceBroker
    stream_broker: RedisStreamBroker
    synthesizer: SpeechSynthesizer
    player: AudioPlayer
    grab: object
    encode: object
    speaking: asyncio.Lock
    turns: asyncio.Queue[PresenceTurn]
    stop: asyncio.Event

    async def close(self) -> None:
        closer = getattr(self.osc, "close", None)
        if callable(closer):
            closer()
        await self.stream_broker.close()


def create_presence_services(*, avatar_path: Path | None = None) -> PresenceServices:
    avatar = load_avatar(avatar_path)
    stream_broker = RedisStreamBroker(
        settings.broker_redis_url,
        stream_maxlen=settings.broker_stream_maxlen,
        dlq_enabled=settings.broker_dlq_enabled,
    )
    streams = BrokerStreams.from_settings(settings)

    return PresenceServices(
        avatar=avatar,
        osc=build_sender(avatar.osc.host, avatar.osc.port),
        broker=PresenceBroker(
            stream_broker,
            streams=streams,
            timeout=settings.broker_rpc_timeout_seconds,
        ),
        stream_broker=stream_broker,
        synthesizer=load_synthesizer(),
        player=DefaultPlayer(),
        grab=default_grab,
        encode=default_encode,
        speaking=asyncio.Lock(),
        turns=asyncio.Queue(),
        stop=asyncio.Event(),
    )


async def stdin_producer(services: PresenceServices) -> None:
    default_name = services.avatar.speaker_name
    while not services.stop.is_set():
        line = await asyncio.to_thread(sys.stdin.readline)
        if line == "":
            services.stop.set()
            return
        turn = parse_ingress_line(line, default_name=default_name)
        if turn is not None:
            await services.turns.put(turn)


async def start_ingress_osc(services: PresenceServices):
    default_name = services.avatar.speaker_name

    def on_packet(address: str, values: tuple[object, ...]) -> None:
        turn = turn_from_osc(address, values, default_name=default_name)
        if turn is not None:
            services.turns.put_nowait(turn)

    return await start_osc_listener(
        services.avatar.osc.host,
        services.avatar.osc.listen_port,
        on_packet,
    )


async def run_presence(services: PresenceServices) -> None:
    await services.broker.ping()
    logger.info("presence broker reachable")

    idle = asyncio.create_task(
        idle_loop(services.osc, services.avatar, services.speaking, services.stop)
    )
    consumer = asyncio.create_task(run_queue(services))
    stdin_task = asyncio.create_task(stdin_producer(services))
    transport = await _try_listen(services)
    try:
        await services.stop.wait()
    finally:
        for task in (idle, consumer, stdin_task):
            task.cancel()
        if transport is not None:
            transport.close()
        await asyncio.gather(idle, consumer, stdin_task, return_exceptions=True)


async def _try_listen(services: PresenceServices):
    try:
        transport, _protocol = await start_ingress_osc(services)
    except OSError:
        logger.warning("presence_osc_listen_failed", exc_info=True)
        return None
    logger.info(
        "presence osc listen %s:%s",
        services.avatar.osc.host,
        services.avatar.osc.listen_port,
    )
    return transport
