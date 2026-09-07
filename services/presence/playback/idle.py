from __future__ import annotations

import asyncio
import math

from services.presence.avatar import AvatarConfig
from services.presence.osc.client import OscSender
from services.presence.osc.messages import float_param


def idle_breath(elapsed: float, *, period: float) -> float:
    if period <= 0:
        return 0.5
    return 0.5 + 0.5 * math.sin(2 * math.pi * elapsed / period)


def idle_look(elapsed: float, *, period: float, amplitude: float) -> float:
    if period <= 0:
        return 0.0
    return amplitude * math.sin(2 * math.pi * elapsed / period)


def send_idle_frame(
    osc: OscSender,
    avatar: AvatarConfig,
    elapsed: float,
) -> None:
    breath = idle_breath(elapsed, period=avatar.idle.breath_period_seconds)
    look = idle_look(
        elapsed,
        period=avatar.idle.look_period_seconds,
        amplitude=avatar.idle.look_amplitude,
    )
    osc.send(*float_param(avatar.parameters.breath, breath))
    osc.send(*float_param(avatar.parameters.look_horizontal, 0.5 + look))


async def idle_loop(
    osc: OscSender,
    avatar: AvatarConfig,
    speaking: asyncio.Lock,
    stop: asyncio.Event,
    *,
    step: float = 0.1,
) -> None:
    if not avatar.idle.enabled:
        await stop.wait()
        return
    elapsed = 0.0
    while not stop.is_set():
        _tick_idle(osc, avatar, speaking, elapsed)
        elapsed += step
        await _sleep_or_stop(stop, step)


def _tick_idle(
    osc: OscSender,
    avatar: AvatarConfig,
    speaking: asyncio.Lock,
    elapsed: float,
) -> None:
    if speaking.locked():
        return
    send_idle_frame(osc, avatar, elapsed)


async def _sleep_or_stop(stop: asyncio.Event, step: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=step)
    except TimeoutError:
        return
